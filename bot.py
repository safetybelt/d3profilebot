#!/usr/bin/python
import time
import praw
import traceback
import re
import logger
import utils
import lookup
import profiler
import formatter

config = utils.get_config_params('reddit_bot')

# get the login info
with open(config['login_file']) as f:
    for l in f:
        setting = ''.join(l.split()).split(':')
        config[setting[0]] = setting[1]

# posts we've searched
#      key: hour the post was posted (0 for 12:00 AM - 12:59, etc)
#      value: list of post_id
#   this structure lets us easily remove lists of posts that are too old
_searched = {}

# submissions we've replied to
#      key: submission_id
#      value: list of dictionaries of hero info we have profiled
#   ensures we don't post the same profile more than once per thread
_replied_to = {}

# failed posts
#       key: post_id
#       value: amount of attempts failed
_failed_posts = {}

# our posts
#     key: post_id
#     value: { 's_id': submission id, 'timestamp': timestamp of our post }
#   we have to check our own posts to remove them at -1 karma.  we'll loop
#       through these and check karma.  remove from this struct after 48 hours
_our_posts = {}

# search terms
#   list of terms we'll search posts for
_search_terms = config['search_terms'].split(',')

def run():
    """ main logic for the bot, just loop through new posts and reply if
        we find a valid post """

    r = _connect()
    subreddit = r.get_subreddit(config['subreddit'])

    _get_our_posts(48*60*60, r)

    while True:

        try:
            # go through sumbissions first
            submissions = subreddit.get_new(limit=50)
            for post in submissions:
                if _filter_check(post):
                    _add_reply(post)

            # go through comments next
            comments = r.get_comments(subreddit, limit=200)
            for post in comments:
                if _filter_check(post):
                    _add_reply(post)

            # check our own posts for negative karma, remove the posts 48 hours+
            _remove_if_necessary(r)
        except Exception, e:
            logger.error('{e}\n{t}\nreconnect in 30 seconds'.format(e=str(e),
                                                    t=traceback.format_exc()))
            time.sleep(30)
            r = _connect()

        time.sleep(10)


def _connect():
    """ Connects to Reddit through PRAW; returns the connection """
    r = praw.Reddit(user_agent = config['user_agent'])
    r.login(config['username'], config['password'])
    return r


def _filter_check(post):
    """ filter posts before trying to search them for valid posts """

    if post.author:
        # don't check our posts
        if post.author.name == config['username'] or post.id in _our_posts:
            logger.debug('{p} is our own post, continue'.format(p=post.id))
            return False
        # don't check posts we've already checked
        hour = _get_hour(post.created_utc)
        if hour in _searched and post.id in _searched[hour]:
            logger.debug('{p} has been checked, continue'.format(p=post.id))
            return False
        # don't check posts older than our max_timeframe setting
        if post.created_utc < time.time() - int(config['max_timeframe']):
            logger.debug('{p} is too old to check, continue'.format(p=post.id))
            return False

        logger.debug('searching {p}'.format(p=post.id))
        return _search(post)

def _search(post):
    """ search through the post for a matching search term """

    hour = _get_hour(post.created_utc)
    if hour not in _searched:
        _searched[hour] = []
    _searched[hour].append(post.id)

    if 'body' in dir(post):
        to_search = post.body
        submission = post.submission
    elif 'selftext' in dir(post):
        to_search = post.selftext
        submission = post
    else:
        logger.warn('Unable to search post {p}'.format(p=post.id))

    for s in _search_terms:
        if s in to_search:
            logger.debug('{p} matched {s}'.format(p=post.id, s=s))
            return True
    return False

def _get_hour(timestamp):
    """ given a timestamp, return the hour it was created """

    return time.strftime('%H', time.gmtime(timestamp))

def _add_reply(post):
    """ given a post that meets the search criteria, reply to it with the 
        text profile; returns true if successful """
    if 'add_comment' in dir(post):
        reply = post.add_comment
        content = post.selftext
        submission = post
    elif 'reply' in dir(post):
        reply = post.reply
        content = post.body
        submission = post.submission
    else:
        logger.warn('Unable to reply to post {p}'.format(p = post.id))

    # hero_info is a dictionary of { 'profile', 'hero' OR 'hero_id', 'region'}
    hero_info = _get_hero_info(content)

    if not hero_info:
        _add_to_failed(post)
        return False

    # make sure we haven't posted this profile in this discussion already
    if submission.id in _replied_to:
        if hero_info in _replied_to[submission.id]:
            logger.info('Already added {p} - {h} in {s}'.format(
                                                    p=hero_info['profile'],
                                                    h=hero_info['hero_id'],
                                                    s=submission.id))
            return False
    else:
        _replied_to[submission.id] = []

    formatted_reply = _create_post(hero_info)
    if not reply:
        logger.warn('Unable to create reply, add to failed')
        _add_to_failed(post)
        return False

    _replied_to[submission.id].append(hero_info)
    r = reply(formatted_reply)
    _our_posts[r.id] = { 'timestamp': r.created_utc, 's_id': submission.id }
    logger.info('Added {p} - {h} in {r} to {sid} - {pid}'.format(
                                        p = hero_info['profile'],
                                        h = hero_info['hero_id'],
                                        r = hero_info['region'],
                                        sid=submission.id,
                                        pid=post.id ))
    return True


def _get_hero_info(content):
    """ given a post content, return a dictionary of:
        { 'profile', 'hero' OR 'hero_id', 'region' }
        (note that if hero_id is found, don't include hero and vice-versa) """

    region = None
    if config['base_url'].format(region='us').replace('http://','') in content:
        region = 'us'
    elif config['base_url'].format(region='eu').replace('http://','') in content:
        region = 'eu'

    if not region:
        logger.warn('No valid URL in post content:\n{c}'.format(c=content))
        return None

    base_url = config['base_url'.format(region=region)]

    t = content.split(base_url)
    if len(t) > 1:
        temp = t[1]
    else:
        temp = t[0]
    hero_id = re.split('\D+', temp.split('hero/')[1])[0]
    profile = temp.split('profile/')[1].split('/hero/')[0]

    return { 'profile': profile, 'hero_id': hero_id, 'region': region }


def _create_post(hero_info):
    """ given hero info (profile, hero_id, region), create a post using the
        formatter """

    profile = hero_info['profile']
    hero_id = hero_info['hero_id']
    region = hero_info['region']
    hero = lookup.hero_lookup(profile, hero_id=hero_id, region=region)

    if not hero:
        logger.warn('Failed to load data for {p} - {h} in {r}'.format(
                                                                p=profile,
                                                                h=hero_id,
                                                                r=region ))
        return None

    intro = profiler.get_intro_info(hero, region=region)
    gear = profiler.get_gear(hero, region=region)
    stats = profiler.get_stats(hero, region=region)
    gear_stats = profiler.get_stats_from_gear(gear, region=region)
    skills = profiler.get_skills(hero, region=region)

    post = []
    post.append(formatter.format_intro(intro))
    post.append(formatter.format_gear(gear))
    post.append(formatter.format_stats(stats, gear_stats=gear_stats))
    post.append(formatter.format_skills(skills))
    post.append(formatter.format_outro())

    return u''.join(post)


def _add_to_failed(post):
    """ given a post, add it to the failed dictionary """

    if post.id in _failed_posts:
        _failed_posts[post.id] += 1
    else:
        _failed_posts[post.id] = 1

    if _failed_posts[post.id] < config['fails_allowed']:
        hour = _get_hour(post.created_utc)
        _searched[hour].remove(post.id)
        logger.info('Failed to create post in {p}, try again'.format(p=post_id))
    else:
        logger.info('Giving up on creating post in {p}'.format(p=post_id))


def _remove_if_necessary(r):
    """ given a reddit connection, check our posts to see if they need 
        to be removed.  if so, remove them.
        also remove all posts from our dictionary older than 48 hours """

    removal_time = time.time() - 48*60*60
    posts_to_delete = []
    for post_id in _our_posts:
        if _our_posts[post_id]['timestamp'] < removal_time:
            posts_to_delete.append(post_id)
            continue

        s_url = 'http://www.reddit.com/r/{s}/comments/{sid}/_/{pid}'.format(
                                s = config['subreddit'],
                                sid=_our_posts[post_id]['s_id'],
                                pid=post_id)
        s = r.get_submission(s_url)

        if not s or not s.comments:
            logger.warn('Failed to find submission at {u}'.format(u=s_url))
            posts_to_delete.append(post_id)
        else:
            post = s.comments[0]

            if post.score < 0:
                logger.info('Removing {s} - {p} due to score ({sc})'.format(
                                                s=_our_posts[post_id]['s_id'],
                                                p=post_id,
                                                sc=post.score))
                post.delete()
                posts_to_delete.append(post_id)

    for p in posts_to_delete:
        del _our_posts[p]


def _get_our_posts(timeframe, r):
    """ called when bot starts up; adds all of our posts in the timeframe to 
        _our_posts and the posts we replied to to _searched (so we don't
        duplicate posts if the bot restarts for any reason) """

    user = r.get_redditor(config['username'])
    comments = user.get_comments(limit=200)

    for comment in comments:
        if comment.created_utc < time.time() - timeframe:
            break

        # we're going to cheat a little and assume our posts was the same
        #   hour as the post it replied to
        hour = _get_hour(comment.created_utc)
        if hour not in _searched:
            _searched[hour] = []

        if '_' in comment.parent_id:
            _searched[hour].append(comment.parent_id.split('_')[1])
        else:
            _searched[hour].append(comment.parent_id)

        _our_posts[comment.id] = {  'timestamp': comment.created_utc,
                                    's_id': comment.submission.id }


if __name__ == '__main__':
    run()
