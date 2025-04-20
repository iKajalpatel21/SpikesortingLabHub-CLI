import  os,\
       sys,\
    logging,\
     shutil
import json
import psutil
from numpy import *
import copy as pycopy
try:
    from .__helpers import *
except:
    from __helpers import *

"""
"""


STEP_DEPENDENCIES = {
    "combined_recording": [],
    "recording": [],
    # Preprocessing needs only a recording
    "preprocessing": [("recording","combined_recording")],
    # Loading a previously done preprocessing doesn't need anything
    "load_preprocessing": [],
    # Sorting also needs only a preprocessing, load_preprocessing, combined_recording OR recording
    "sorting": [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing")
    ],
    # Load a previously done sorting
    "load_sorting": [],
    # Analyzer: the firs argument is a preprocessing, combined_recording, load_preprocessing OR recording, the second is sorting OR load_sorting
    "analyzer": [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting")
    ],
    # Load a previously done analyzer
    "load_analyzer": [],
    # Exporting to phy: the firs argument is a preprocessing, load_preprocessing, combined_recording OR recording, the second is sorting  OR load_sorting
    "phy_export" : [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting")
    ],
    # Importing from phy needs: the only argument is a preprocessing, load_preprocessing, combined_recording OR recording
    "import_from_phy" : [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing")
    ],
    # Report requires: the first argument is a preprocessing, load_preprocessing, combined_recording OR recording, the second is sorting  OR load_sorting, the last is analyzer OR load_analyzer
    "report": [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting"),
        ("analyzer","load_analyzer")
    ],
    # Export to MatLab requires sorting OR load_sorting AND analyzer OR load_analyzer
    "export2matlab": [
        ("sorting","load_sorting"),
        ("analyzer","load_analyzer")
    ],
    # Upload whatever was done!
    "upload": [],
}

STEP_PARAMETERS = {
    "combined_recording" : {
    },
    "recording"    : {
    },
    "preprocessing": {
        "required" : [ ("methods",list) ],
        "optional" : [
            ("centering",dict), 
            ("highpass or band filtering",dict),
            ("referensing",dict),
            ("whitening",dict),
            ("zscore",dict),
            ("folder",str)
        ] 
    },
    "load_preprocessing": {
        "required" : [ ("folder",str) ]
    },
    "sorting"      : {
        "required" : [
            ("name",str),
            ("parameters",dict)
        ],
        "optional" : [ ("folder",str) ]
    },
    "load_sorting" : {
        "required" : [ ("folder",str) ]
    },
    "analyzer"     : {
    },
    "load_analyzer": {
        "required" : [ ("folder",str) ]
    },
    "phy_export"   : {
        "optional" : [ ("folder",str) ]
    },
    "import_from_phy" : {
        "required" : [ ("folder",str) ]
    },
    "export2matlab": {
        "optional" : [ ("filename",str) ]
    },
    "upload"       : {
        "required" : [
            ("keep_base_directory",bool),
            ("destination",str)
        ],
        "optional" : {
            ("suffix",str)
        }
    }
}

# with open('__sorting_sanity.json') as fd:
    # j = json.load(fd)

# SORTING_SANITY,SI_VERSION = j['SORTING_SANITY'],j['SI_VERSION']
    

def job_sanity(config:dict):
    logger = logging.getLogger( 'job_sanity_check' )
    for required_job_item,item_type in [('version',str), ('job_id',str), ('job_evn',dict), ('job_steps',list)]:
        if not required_job_item in config:
            logger.error(f'There is no required item `{required_job_item}` in the job configuration')
            raise RuntimeError(f'There is no required item `{required_job_item}` in the job configuration')
        if not type(config[required_job_item]) is item_type:
            logger.error(f'Configuration item `{required_job_item}` has a wrong type {type(config[required_job_item])}, but should be {item_type}')
            raise RuntimeError(f'Configuration item `{required_job_item}` has a wrong type {type(config[required_job_item])}, but should be {item_type}')

    if config['version'] != "0.4.1":
        logger.error(f'The configuration has a wrong version')
        raise RuntimeError(f'The configuration has a wrong version')

    if len(config['job_id']) < 2:
        logger.error(f'job_id should be at least 2 characters long.')
        raise RuntimeError(f'job_id should be at least 2 characters long.')

    for required_job_env,item_type in [("base directory",str),("job_kwarg",dict)]:
        if not required_job_env in config['job_evn']:
            logger.error(f'The required job environment `{required_job_env}` is not set')
            raise RuntimeError(f'The required job environment `{required_job_env}` is not set')
        if not type(config['job_evn'][required_job_env]) is item_type:
            logger.error('The environment variable `{}` has a wrong type {}, but should be {}'.format(required_job_env,type(config['job_evn'][required_job_env]),item_type))
            raise RuntimeError('The environment variable `{}` has a wrong type {}, but should be {}'.format(required_job_env,type(config['job_evn'][required_job_env]),item_type))
    #optional variables
    if 'log_level' in config['job_evn']:
        if not type(config['job_evn']['log_level']) is str:
            logger.error('The environment variable `log_level` has a wrong type {}, but should be a string'.format(type(config['job_evn']['log_level'])))
            raise RuntimeError('The environment variable `log_level` has a wrong type {}, but should be a string'.format(type(config['job_evn']['log_level'])))
        if not config['job_evn']['log_level'] in 'NOTSET DEBUG WARNING ERROR CRITICAL'.split():
            logger.error('The environment variable `log_level` has a wrong value {}, but should be one of these: NOTSET DEBUG WARNING ERROR CRITICAL'.format(config['job_evn']['log_level']))
            raise RuntimeError('The environment variable `log_level` has a wrong value {}, but should be one of these: NOTSET DEBUG WARNING ERROR CRITICAL'.format(config['job_evn']['log_level']))
    
    if "REDIRECT" in config['job_evn']:
        if not type(config['job_evn']['REDIRECT']) is dict:
            logger.error('The environment variable `REDIRECT` has a wrong type {}, but should be a dictionary'.format(type(config['job_evn']['REDIRECT'])))
            raise RuntimeError('The environment variable `REDIRECT` has a wrong type {}, but should be a dictionary'.format(type(config['job_evn']['REDIRECT'])))
        for rdr in config['job_evn']['REDIRECT']:
            if not rdr in 'log out err'.split():
                logger.error(f'Unknown REDIRECT entrance {rdr}. Can redirect only log, out or err streams')
                raise RuntimeError(f'Unknown REDIRECT entrance {rdr}. Can redirect only log, out or err streams')
            if not type(config['job_evn']['REDIRECT'][rdr]) is str:
                logger.error(f'REDIRECT entrance {rdr} has a wrong type. It should be a string only')
                raise RuntimeError(f'REDIRECT entrance {rdr} has a wrong type. It should be a string only')
    if 'envs' in config['job_evn']:
        if not type(config['job_evn']['envs']) is dict:
            logger.error('The environment variable `envs` has a wrong type {}, but should be a dictionary'.format(type(config['job_evn']['envs'])))
            raise RuntimeError('The environment variable `envs` has a wrong type {}, but should be a dictionary'.format(type(config['job_evn']['envs'])))
        for env in config['job_evn']['envs']:
            if not type(config['job_evn']['envs'][env]) is str:
                logger.error(f'envs entrance {env} has a wrong type. It should be a string only')
                raise RuntimeError(f'envs entrance {env} has a wrong type. It should be a string only')
    return 0


def steps_sanity(config:dict):
    logger = logging.getLogger( 'steps_sanity_check' )
    steps = config['job_steps']
    if len(steps) < 1:
        logger.error('job_steps list is empty')
        raise RuntimeError('job_steps list is empty')
    prev_steps_ids = []
    prev_steps_fun = []
    for sid,s in enumerate(steps):
        if not type(s) is dict:
            logger.error(f'step #{sid+1} has a incorrect type {type(s)}, but should be a dictionary')
            raise RuntimeError(f'step #{sid+1} has a incorrect type {type(s)}, but should be a dictionary')
        for required_step_item, item_type in [('function',str), ('identifier',str), ('depends',list) ] :
            if not required_step_item in s:
                logger.error(f'required step key `{required_step_item}` is missing in the step #{sid+1}')
                raise RuntimeError(f'required step key `{required_step_item}` is missing in the step #{sid+1}')
            if not type(s[required_step_item]) is item_type:
                logger.error(f'required step key `{required_step_item}` in the step #{sid+1} has an incorrect type {type(s[required_step_item])} but should be {item_type}')
                raise RuntimeError(f'required step key `{required_step_item}` in the step #{sid+1} has an incorrect type {type(s[required_step_item])} but should be {item_type}')
        for itm in s:
            if not itm in  'function identifier depends'.split():
                logger.error(f'Unknown entrance {itm} in step #{sid+1}')
                raise RuntimeError(f'Unknown entrance {itm} in step #{sid+1}')
        if not s['function'] in STEP_DEPENDENCIES:
            logger.error('Unknown function `'+s['function']+f'` in step #{sid+1}. Should be one of these: '+', '.join([_ for _ in STEP_DEPENDENCIES]))
            raise RuntimeError('Unknown function `'+s['function']+f'` in step #{sid+1}. Should be one of these: '+', '.join([_ for _ in STEP_DEPENDENCIES]))
        
        if s['identifier'] in prev_steps_ids:
            logger.error('The identifier `{}` is not unique! Step #{} has the same identifier'.format(s['identifier'], prev_steps_ids.index(s['identifier'])+1) )
            raise RuntimeError('The identifier `{}` is not unique! Step #{} has the same identifier'.format(s['identifier'], prev_steps_ids.index(s['identifier'])+1) )
        allowed_dependencies = STEP_DEPENDENCIES[ s['function'] ] 
        if len(allowed_dependencies) != len(s['depends']):
            logger.error('Too many or Not enough dependencies in step #{}. Needs {} but given {}'.format(sid+1,len(allowed_dependencies),len(s['depends'])) )
            raise RuntimeError('Too many or Not enough dependencies in step #{}. Needs {} but given {}'.format(sid+1,len(allowed_dependencies),len(s['depends'])) )
        for depid,dep in enumerate(s['depends']):
            if not dep in prev_steps_ids:
                logger.error(f'There is no previous step with ID{dep} required for current step #{sid+1}' )
                raise RuntimeError(f'There is no previous step with ID{dep} required for current step #{sid+1}' )
            reffun = prev_steps_fun[ prev_steps_ids.index(dep) ]
            if type(allowed_dependencies[depid]) is str and allowed_dependencies[depid] == reffun: pass
            elif (type(allowed_dependencies[depid]) is list or type(allowed_dependencies[depid]) is tuple) and reffun in allowed_dependencies[depid]: pass
            else:
                logger.error(f'Dependence {dep} for current step #{sid+1} has an incorrect function {reffun} but should be (one of these) `{allowed_dependencies[depid]}`')
                raise RuntimeError(f'Dependence {dep} for current step #{sid+1} has an incorrect function {reffun} but should be (one of these)  `{allowed_dependencies[depid]}`')
        prev_steps_ids.append( s['identifier'] )
        prev_steps_fun.append( s['function'] )
    return 0
            
                
if __name__ == '__main__':
    with open(sys.argv[1]) as fd:
        j = json.load(fd)
    
    print( job_sanity(j) )
    print( steps_sanity(j) )
        
        
    

