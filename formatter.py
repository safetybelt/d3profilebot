import sqlite3
import utils
import logger

config = utils.get_config_params('formatter')

def format_gear(gear):
    """ given a dictionary of gear { item_slot: { item_info } }, return
        a formatted string to send to a reddit post """

    items = {}
    intro = '\n\n######&nbsp;\n\n****\n**Equipped Gear:**\n\n'

    try:
        # open a db connection
        db = sqlite3.connect(config['database'])
        db.row_factory = sqlite3.Row
        db_cur = db.cursor()
        table = config['item_table']
        query = 'SELECT * FROM {t} WHERE name=\'{s}\''

        # get the max order here (useful to remove secondary effects, etc)
        max_order = int(config['max_order'])

        for slot in gear:
            name = _create_url(gear[slot]['name'], gear[slot]['url'])
            i_type = gear[slot]['type']
            item_info = u'> **{n} ({t})**'.format(n=name, t=i_type)
            # because blizzard randomly uses a non-standard apostrophe sometimes
            item_info = item_info.replace(u'\u2019', '\'')

            d_stats = {}
            for stat in gear[slot]['stats']:
                db_cur.execute(query.format(t=table, s=stat['name']))
                row = db_cur.fetchone()
                if row['display'] and row['disp_order'] < max_order:
                    # we send the min AND max values; min is generally only one 
                    #   that is shown and matters, but a few stats need both
                    a_min = stat['min']
                    a_max = stat['max']
                    order = row['disp_order']
                    display = row['display'].format(a_min, a_max)
                    d_stats[order] = display

            # add all gems together (if possible) and display them
            if 'gems' in gear[slot]:
                gem_data = {}
                for gem in gear[slot]['gems']:
                    attr_name = gem['attr']
                    if attr_name in gem_data:
                        gem_data[attr_name] += gem['val']
                    else:
                        gem_data[attr_name] = gem['val']

                d_count = max_order + 1
                for attr in gem_data:
                    db_cur.execute(query.format(t=table, s=attr))
                    row = db_cur.fetchone()
                    if row['display']:
                        a_min = gem_data[attr]
                        display = row['display'].format(a_min)

                        d_stats[d_count] = '{d} (gems)'.format(d=display)
                        d_count += 1


            stat_text = ' | '.join([d_stats[s] for s in sorted(d_stats)])
            item_stats = ''.join(('> ', stat_text))
            
            passive_text = ' | '.join(p for p in gear[slot]['passives'])
            if passive_text:
                item_pass = ''.join(('> ', _italic_superscript(passive_text)))
            else:
                item_pass = ''

            items[slot] = '    \n'.join((item_info, item_stats, item_pass))
    except sqlite3.Error, e:
        logger.error('SQLite3 Error in get_gear: {e}'.format(e=e.args[0]))
        utils.rollback_db(db)
    finally:
        utils.close_db(db)

    # get the order we want gear to display
    slot_disp = config['item_display_order'].split(',')

    disp = []
    for slot in slot_disp:
        if slot in items:
            disp.append(items[slot])

    stats = u'\n\n'.join(disp)
    return u''.join((intro, stats))

def format_stats(stats, gear_stats=None):
    """ given a dictionary of {'stat': value}, return a formatted string to 
        send to a reddit post """

    intro = '\n\n######&nbsp;\n\n****\n**Character Stats:**\n\n'
    try:
        # open a db connection
        db = sqlite3.connect(config['database'])
        db.row_factory = sqlite3.Row
        db_cur = db.cursor()
        table = config['stats_table']
        query = 'SELECT * FROM {t} WHERE name=\'{s}\''

        char_stats = {}
        max_val_len = 0
        max_name_len = 0
        stat_text = []

        for stat in stats:
            db_cur.execute(query.format(t=table, s=stat))
            row = db_cur.fetchone()
            if row['display'] and row['disp_name']:
                val = stats[stat]
                # don't display stats at 0 or the low primary stats
                if val == 0 or (row['primary_stat'] == 1 and val < 100):
                    continue
                disp_val = row['display'].format(val)
                order = row['disp_order']
                disp_name = row['disp_name']
                char_stats[order] = ( disp_name, disp_val )
                if len(disp_val) > max_val_len:
                    max_val_len = len(disp_val)
                if len(disp_name) > max_name_len:
                    max_name_len = len(disp_name)

        if gear_stats:
            for stat in gear_stats:
                db_cur.execute(query.format(t=table, s=stat))
                row = db_cur.fetchone()
                if row['display'] and row['disp_name']:
                    val = gear_stats[stat]
                    # crit has a base of 5%; add it here
                    if stat == 'Crit_Percent_Bonus_Capped':
                        val += 5
                    # don't display stats at 0 or the low primary stats
                    if val == 0 or (row['primary_stat'] == 1 and val < 100):
                        continue
                    disp_val = row['display'].format(val)
                    order = row['disp_order']
                    disp_name = row['disp_name']
                    char_stats[order] = ( disp_name, disp_val )
                    if len(disp_val) > max_val_len:
                        max_val_len = len(disp_val)
                    if len(disp_name) > max_name_len:
                        max_name_len = len(disp_name)


        for order in sorted(char_stats):
            name = char_stats[order][0]
            val = char_stats[order][1]
            sp = ' ' * (max_name_len - len(name))
            stat_text.append('  '.join(('  ', sp, name, val, '\n')))

        return u''.join((intro, u''.join(stat_text)))

    except sqlite3.Error, e:
        logger.error('SQLite3 Error in get_gear: {e}'.format(e=e.args[0]))
        utils.rollback_db(db)
    finally:
        utils.close_db(db)

def format_skills(skills):
    """ given a dictionary of:
        { 'active': [{ 'name': skill name, 'rune': rune name, 'url': url },...],
          'passive': [{ 'name': s1, 'url': url }, ... ] }
        return a fromatted string ready to post to reddit """
    skills_table = []
    skills_table.append('\n\n######&nbsp;\n\n****\n**Character Skills:**\n\n')

    skills_table.append('> **Active:**\n')
    skills_table.append('> | | | | | | |')
    skills_table.append('> |:-:|:-:|:-:|:-:|:-:|:-:|')
    active = ['> |']
    rune = ['> |']
    for skill in skills['active']:
        skill_name = _create_url(skill['name'], skill['url'])
        active.append('{s}|'.format(s=skill_name))
        rune.append('{r}|'.format(r=skill['rune']))
    skills_table.append(u''.join(active))
    skills_table.append(u''.join(rune))

    skills_table.append('\n> **Passive:**\n')
    skills_table.append('> | | | | |')
    skills_table.append('> |:-:|:-:|:-:|:-:|')
    passive = ['> |']
    for skill in skills['passive']:
        skill_name = _create_url(skill['name'], skill['url'])
        passive.append('{s}|'.format(s=skill_name))
    skills_table.append(u''.join(passive))

    return u'\n'.join(skills_table)

def format_intro(hero_info):
    """ given a dictionary of hero info, return a formatted intro string ready
        to post to reddit """

    name = _create_url(hero_info['name'], hero_info['url'])
    level = hero_info['level']
    p_level = hero_info['paragon_level']
    hardcore = hero_info['hardcore']
    h_class = hero_info['class']
    intro = u'### **Text Profile for {n}** - {l} (PL {pl}) {hc} {c}'.format(
                        n=name, l=level, pl=p_level, hc=hardcore, c=h_class )
    return intro

def format_outro():
    """ return a footer string formatted for reddit post """

    message_me = _create_url('^message ^me', config['message_me'])
    next_up = 'better stat layout; set bonuses'
    outro = ['\n\n#&nbsp;\n']
    outro.append(_super('bot is a work in progress | '))
    outro.append(' {m} ^with ^suggestions '.format(m=message_me))
    # outro.append(_super(' | next todo: {n}'.format(n=next_up)))
    outro.append('    \n')
    outro.append(_super('this post will remove itself at negative karma'))

    return u''.join(outro)


def _create_url(text, url):
    """ given text and a url, create the reddit version of a link.  if the url
        is set to None, just return the text """

    if not url:
        return text
    return u'[{t}]({u})'.format(t=text, u=url)

def _italic_superscript(text):
    """ given text, return the same text in italicized superscript format """
    t =  u' ^'.join(text.split())
    return u''.join(('*^', t, '*'))

def _super(text):
    """ given text, return superscript format """
    t = u' ^'.join(text.split())
    return u''.join(('^', t))