import  os,\
       sys,\
    logging,\
     shutil
import json
import psutil
from numpy import *
import copy as pycopy
from .__helpers import * 

"""
"""


STEP_DEPENDENCIES = {
    "recording": [],
    # Preprocessing needs only a recording
    "preprocessing": ["recording"],
    # Loading a previously done preprocessing doesn't need anything
    "load_preprocessing": [],
    # Sorting also needs only a preprocessing, load_preprocessing OR recording
    "sorting": [
        ("recording", "preprocessing", "load_preprocessing")
    ],
    # Load a previously done sorting
    "load_sorting": [],
    # Analyzer: the firs argument is a preprocessing, load_preprocessing OR recording, the second is sorting OR load_sorting
    "analyzer": [
        ("recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting")
    ],
    # Load a previously done analyzer
    "load_analyzer": [],
    # Exporting to phy: the firs argument is a preprocessing, load_preprocessing OR recording, the second is sorting  OR load_sorting
    "phy_export" : [
        ("recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting")
    ],
    # Importing from phy needs: the first argument is a preprocessing, load_preprocessing OR recording, the second is sorting  OR load_sorting, the last one is an phy_export
    "import_phy" : [
        ("recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting"),
        "phy_export" 
    ],
    # Report requires: the first argument is a preprocessing, load_preprocessing OR recording, the second is sorting  OR load_sorting, the last is analyzer OR load_analyzer
    "report": [
        ("recording", "preprocessing", "load_preprocessing"),
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
    # if 'log_level' in config['job_evn']:
        
        
        

# def steps_sanity(config:dict):
    

