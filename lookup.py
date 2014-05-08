import sys
import urllib2
import json
import utils
import logger

config = utils.get_config_params('d3_lookup')

def _api_call(url, region):
    """ make a call to the d3 api in the given region
        returns a python dictionary (converted from the json returned) """
    base_url = config['base_url'].format(region=region)
    api_url = '{base}{url}'.format(base=base_url, url=url)

    try:
        logger.debug('Loading: {url}'.format(url=api_url))
        data = urllib2.urlopen(api_url).read()
        data = json.loads(data)

        # api error returend
        if 'code' in data:
            reason = data['reason']
            logger.warn('API error: {r} on {url}'.format(r=reason, url=api_url))
            return None
        return data
    except urllib2.HTTPError, e:
        error = e.code
        logger.error('HTTP error: {e} on {url}'.format(e=error, url=api_url))
    except urllib2.URLError, e:
        error = e.reason.args[1]
        logger.error('Network error: {e} on {url}'.format(e=error, url=api_url))
    return None

def hero_lookup(profile, hero=None, hero_id=None, region='us'):
    """ look up a profile and return the hero data.
        if hero_id is provided, use that.  if hero name is provided, find the
        highest level, most recently played hero with the matching name from
        that profile and use that.  if neither are provided, use the highest
        level, most recently played hero on the profile """

    if not hero_id:
        hero_id = _get_hero_id(profile, region, hero)
    api_url = 'profile/{profile}/hero/{id}'.format(profile=profile, id=hero_id)

    # add the profile data to the dictionary, we'll need it later
    info = _api_call(api_url, region=region)
    info['profile'] = profile
    return info

def _get_hero_id(profile, region, hero_name=None):
    """ get the hero id for the given profile
        if hero name is provided, return the id for the highest level, most
        recently played match. if not, use the highest level, most recently 
        played hero """

    api_url = 'profile/{profile}/'.format(profile=profile)
    data = _api_call(api_url, region=region)

    if data:
        if hero_name:
            matches = {}
            matched_level = 0
            for hero in data['heroes']:
                if hero['name'].lower() == hero_name.lower():
                    matches[hero['id']] = hero['last-updated']
                    matched_level = hero['level']
                elif hero['level'] < matched_level:
                    break

            if matches:
                # return the most recently played match
                heroes = sorted(matches, key=lambda x: matches[x])
                heroes.reverse()
                return heroes[0]
            return None
        else:
            # api returns them sorted (level, timestamp) so return first hero
            return data['heroes'][0]['id']
    return None

def item_lookup(item, is_item_name=False, region='us'):
    """ given an item string, return the item data
        expects a tooltipParam type item string (item/Cr0BCLqtqLoEEgcIB...)
        if the item is an actual blizzard item name ("Mempo's Twilight",
        "Rabid Strike", etc), set is_item_name to True convert """
    if is_item_name:
        item = _convert_item_name(item)
    api_url = 'data/{item_url}'.format(item_url=item)

    return _api_call(api_url, region=region)

def _convert_item_name(item):
    """ converts an item name into one that blizzard api understands """
    item = item.lower().replace('-','').replace(' ','-').replace('\'', '')
    return 'item/{item}'.format(item=item)