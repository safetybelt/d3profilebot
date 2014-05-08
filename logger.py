import time
import traceback
import utils

config = utils.get_config_params('logging')

def get_file_path():
    """ Returns the file path for the log file """

    file_path = (config['log_location'], config['log_file'])
    return '{path}/{file}'.format(path=file_path[0], file=file_path[1])

def debug(entry):
    """ Log entry if log_level is set to debug or lower """

    if _get_log_level() <= 0:
        _log('DEBUG - {entry}'.format(entry=entry))

def info(entry):
    """ Log entry if log_level is set to info or lower """
    
    if _get_log_level() <= 1:
        _log('INFO - {entry}'.format(entry=entry))

def warn(entry):
    """ Log entry if log_level is set to warn or lower """
    
    if _get_log_level() <= 2:
        _log('WARN - {entry}'.format(entry=entry))

def error(entry):
    """ Log entry if log_level is set to error or lower """
    
    if _get_log_level() <= 3:
        _log('ERROR - {entry}'.format(entry=entry))

def fatal(entry):
    """ Log entry if log_level is set to fatal or lower """
    
    if _get_log_level() <= 4:
        _log('FATAL - {entry}'.format(entry=entry))


def _log(entry):
    """ Logs the entry with a timestamp in our log file """
    
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    try:
        loc = config['log_location']
        filename = config['log_file']
        file_path = get_file_path()
        f = open(file_path, 'a')
        f.write('{t} - {e}\n'.format(t=timestamp, e=str(entry)))
        f.close()
    except Exception, e:
        f = open('d3logging.err', 'a')
        f.write('{t} -\n{tb}\n'.format(t=timestamp, tb=traceback.format_exc()))
        f.close()
        raise

def _get_log_level():
    """ returns the numerical value of the current log_level
            debug = 0
            info  = 1
            warn  = 2
            error = 3
            fatal = 4
        default value is 1
    """
    return {
        'debug': 0,
        'info': 1,
        'warn': 2,
        'error': 3,
        'fatal': 4
        }.get(config['log_level'], 1)
