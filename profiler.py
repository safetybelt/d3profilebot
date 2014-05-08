import time
import sqlite3
import lookup
import utils
import logger

config = utils.get_config_params('profiler')

def get_gear(hero_data, region='us'):
    """ given a dictionary of hero data, get the gear and return it in a
        dictionary of { item_slot: { item_info } } use region to get proper
        urls """

    gear = {}

    try:
        # open a db connection
        db = sqlite3.connect(config['database'])
        db_cur = db.cursor()
        table = config['item_table']

        for slot, item in hero_data['items'].iteritems():
            item_url = item['tooltipParams']
            item_data = lookup.item_lookup(item_url, region=region)

            if not item_data:
                logger.error('Unable to load item {i}'.format(i=item_url))
                utils.close_db(db)
                return None

            gear[slot] = {
                            'name': item_data['name'],
                            'type': item_data['typeName']
                         }

            # get the url for legendaries/set items
            if 'Legendary' in gear[slot]['type'] or 'Set' in gear[slot]['type']:
                gear[slot]['url'] = _get_item_url(item_data, region)
            else:
                gear[slot]['url'] = None

            # get any passive effects text
            gear[slot]['passives'] = []
            for passive in item_data['attributes']['passive']:
                # replace all whitespace (newlines included) with a space
                gear[slot]['passives'].append(' '.join(passive['text'].split()))

            # get raw attributes (used for custom display + stat calculation)
            gear[slot]['stats'] = []
            for attr in item_data['attributesRaw']:
                # check if attribute name is in database; if not, add it and log
                query = 'SELECT * FROM {t} WHERE name=\'{a}\''
                db_cur.execute(query.format(t=table,a=attr))

                row = db_cur.fetchone()
                if not row:
                    logger.info('Adding {a} to {t}'.format(a=attr, t=table))
                    query = 'INSERT INTO {t}(name,multiplier) VALUES(\'{a}\',1)'
                    db_cur.execute(query.format(t=table,a=attr))

                # multiply values by the multiplier
                query = 'SELECT multiplier FROM {t} WHERE name=\'{a}\''
                db_cur.execute(query.format(t=table,a=attr))
                row = db_cur.fetchone()
                a_min = item_data['attributesRaw'][attr]['min'] * row[0]
                a_max = item_data['attributesRaw'][attr]['max'] * row[0]

                # if this is a damage_min, change the max value to be min+delta 
                dmg = ['Damage_Weapon_Min', '_Weapon_Bonus_Min', 'Damage_Min']
                if dmg[0] in attr or dmg[1] in attr or dmg[2] == attr:
                    attr_d = attr.replace('Min','Delta')
                    a_max = item_data['attributesRaw'][attr_d]['max'] * row[0]
                    a_max += a_min
                # if this is a bleed chance, set max value to be the damage
                elif 'Weapon_On_Hit_Percent_Bleed_Proc_Chance' == attr:
                    dmg = 'Weapon_On_Hit_Percent_Bleed_Proc_Damage'
                    db_cur.execute(query.format(t=table,a=dmg))
                    row = db_cur.fetchone()
                    if dmg in item_data['attributesRaw']:
                        a_max = item_data['attributesRaw'][dmg]['min'] * row[0]
                    else:
                        a_max = 0

                gear[slot]['stats'].append( {
                                                'name': attr,
                                                'min': a_min,
                                                'max': a_max
                                            } )

            # get gem info - note we only keep MAX value; gems don't have ranges
            if item_data['gems']:
                gear[slot]['gems'] = []
                query = 'SELECT multiplier FROM {t} WHERE name=\'{a}\''
                for gem in item_data['gems']:
                    for attr in gem['attributesRaw']:
                        db_cur.execute(query.format(t=table,a=attr))
                        row = db_cur.fetchone()
                        value = gem['attributesRaw'][attr]['max'] * row[0]
                        gear[slot]['gems'].append({ 'attr': attr, 'val': value})
            db.commit()
    except sqlite3.Error, e:
        logger.error('SQLite3 Error in get_gear: {e}'.format(e=e.args[0]))
        utils.rollback_db(db)
    finally:
        utils.close_db(db)

    return gear


def _get_item_url(item_data, region):
    """ given a dictionary of item data, return the item url """
    item_url = 'item/{id}'.format(id=item_data['id'])
    base_data = lookup.item_lookup(item_url, region=region)
    base = config['base_url'].format(region=region)
    item = base_data['tooltipParams'].replace('item/','').replace('recipe/','')

    # crafted items have a different url
    if item_data['craftedBy'] != []:
        path = config['crafted_item_url']
    else:
        path = config['item_url']

    full_url = '{b}{p}{i}'.format(b=base, p=path, i=item)

    return full_url


def get_stats(hero_data, region='us'):
    """ given a dictionary of hero data, return a dictionary of {'stat': value}
        note that the stat name will be in API form, not displayable form """

    stats = {}

    try:
        # open a db connection
        db = sqlite3.connect(config['database'])
        db.row_factory = sqlite3.Row
        db_cur = db.cursor()
        table = config['stats_table']
        query = 'SELECT * FROM {t} WHERE name=\'{s}\''

        for stat in hero_data['stats']:
            db_cur.execute(query.format(t=table,s=stat))
            row = db_cur.fetchone()
            s = hero_data['stats'][stat] * row['multiplier']
            stats[stat] = s

        return stats
    except sqlite3.Error, e:
        logger.error('SQLite3 Error in get_stats: {e}'.format(e=e.args[0]))
        utils.rollback_db(db)
    finally:
        utils.close_db(db)


def get_stats_from_gear(gear, region='us'):
    """ given a gear dictionary (created by get_gear), return the stats listed
        in the config file """

    g_stats = dict.fromkeys(config['gear_stats'].split(','), 0)

    for slot in gear:
        for stat in gear[slot]['stats']:
            if stat['name'] in g_stats:
                val = stat['min']
                g_stats[stat['name']] += val

    return g_stats



def get_skills(hero_data, region='us'):
    """ given a dictionary of hero data, return a dictionary of:
        { 'active': [{ 'name': skill name, 'rune': rune name, 'url': url },...],
          'passive': [{ 'name': s1, 'url': url }, ... ] } """

    skills = { 'active': [], 'passive': [] }
    for ability in hero_data['skills']['active']:
        name = None
        rune = None
        url = None
        if ability:
            name = ability['skill']['name']
            url = _get_skill_url(ability, 'active', region)
            if 'rune' in ability.keys():
                rune = ability['rune']['name']
        skills['active'].append({'name': name, 'rune': rune, 'url': url})
    for ability in hero_data['skills']['passive']:
        name = None
        url = None
        if ability:
            name = ability['skill']['name']
            url = _get_skill_url(ability, 'passive', region)
        skills['passive'].append({'name': name, 'url': url})

    return skills

def get_intro_info(hero_data, region='us'):
    """ given a dictionary of hero data, return a dictionary of:
        { 'name': name, 'url': url, 'class': class, 'hardcore': hardcore,
          'level': level, 'paragon_level': paragon level } """

    hero_info = {
                    'name':     hero_data['name'],
                    'url':      _get_hero_url(hero_data, region),
                    'class':    hero_data['class'].title().replace('-', ' '),
                    'hardcore': 'Hardcore' if hero_data['hardcore'] else '',
                    'level':    hero_data['level'],
                    'paragon_level':    hero_data['paragonLevel']
                }

    return hero_info


def _get_skill_url(skill_data, skill_type, region):
    """ given a dictionary of skill data and the skill_type (active or passive),
        return the skill url """

    base = config['base_url'].format(region=region)
    # tooltipUrl always like: 'skill/{class}/{skill}'
    split_tt = skill_data['skill']['tooltipUrl'].split('/')
    h_class = split_tt[1]
    skill = split_tt[2]

    skill_url = '{b}/class/{c}/{t}/{s}'.format(
                                                b=base,
                                                c=h_class,
                                                t=skill_type,
                                                s=skill
                                              )

    return skill_url


def _get_hero_url(hero_data, region):
    """ given a dictionary of hero data, return the hero url """
    base = config['base_url'].format(region=region)
    profile = hero_data['profile']
    hero_id = hero_data['id']
    hero_url = '{b}/profile/{p}/hero/{h}'.format(b=base, p=profile, h=hero_id)
    return hero_url