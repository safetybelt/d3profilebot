def get_config_params(section_name, filename='d3profilebot.config'):
    """ get the config parameters and values from the given section (logging,
        bot, etc); return a dictionary of { 'param': 'value' } """

    with open(filename) as f:
        config = {}
        in_section = False

        for line in f:
            if in_section and not line == '\n':
                setting = ''.join(line.split()).split(':')
                value = setting[1]

                if len(setting) > 2:
                    # build a string for all settings[1+]
                    for i in range(2, len(setting)):
                        value = ''.join([value, ':', setting[i]])

                config[setting[0]] = value
            elif in_section and line == '\n':
                break
            elif '[{section}]'.format(section=section_name) in line:
                in_section = True
    return config



def close_db(database):
    """ close the given sqlite3 database connection """
    if database:
        database.close()

def rollback_db(database):
    """ roll back the given sqlite3 database """
    if database:
        database.rollback()