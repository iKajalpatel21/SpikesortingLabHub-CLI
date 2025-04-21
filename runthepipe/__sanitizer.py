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


def sanetize_sorting(config:dict):
    
    with open('__sorting_sanity.json') as fd:
        j = json.load(fd)

    SORTING_SANITY,SI_VERSION = j['SORTING_SANITY'],j['SI_VERSION']

    return 0            

# The first character of the name defines where it is *required or >optional parameter,
# if a value is a tuple - it is a choice.
# if a value is a list with one element - any number of elements are allowed, 
#    otherwise number of elements should be strictly equal to the number of elements in the list.
STEP_PARAMETERS = {
    "combined_recording" : {
    },
    "recording"    : (
            {
                '*binfile'            : str,
                '*probe'              : str,
                '*sampling rate'      : (int, float),
                '*number of channels' : int,
                ">remove"             : [ int ],
                ">bad_channels"       : [ int ],
                ">location"           : str,
                ">gain_to_uV"         : (int, float),
                ">offset_to_uV"       : (int, float)
            },
            {
                '*neuralynx'          : str
            }
    ),
    "preprocessing": {
        "*methods": [ str ] ,
        ">centering" : {
            '>mode': ('median', 'mean')
        }, 
        ">highpass or band filtering" : {
            '>btype' : ('bandpass', 'highpass'),
            '>band'  : (float, [float,float])
        },
        ">referensing" : { 
            '>reference': ('global', 'single', 'local'),
            '>operator' : ('median', 'average'),
            '>groups'   : ( [int]  ,  None ),
            '>local_radius' : [int, int],
            '>ref_channel_ids' : [int]
        },
        ">whitening" : {
            '>mode'      : ('global', 'local'),
            '>radius_um' : (float, None), 
            '>apply_mean': bool,
            '>int_scale' : (float, None),
            '>eps'       : (float, None)
        },
        ">zscore": {
            '>mode' : ('median+mad', 'mean+std')
        },
        "folder":str
    },
    "load_preprocessing": {
        "*folder": str
    },
    "sorting"      : {
        "*name"       : str,
        "*parameters" : dict,
        ">folder"     : str,
        ">image"      : str
    },
    "load_sorting" : {
        "*folder"  : str
    },
    "analyzer"     : {
    },
    "load_analyzer": {
        "*folder"  : str
    },
    "phy_export"   : {
        ">folder"  : str
    },
    "import_from_phy" : {
        ">folder"  : str
    },
    "export2matlab": {
        ">filename": str
    },
    "upload"       : {
        "*destination"        : str,
        ">keep_base_directory": bool,
        ">suffix"             : str
    }
}
    

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


def job_steps_sanity(config:dict):
    logger = logging.getLogger( 'job_steps_sanity_check' )
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

def steps_sanity(config:dict):
    def check_an_enry(entry,sch):
        
        if   type(sch) is tuple:
            logger.debug(f"TUPLE > {entry} {sch}")
            for s in sch:
                x = check_an_enry(entry,s)
                logger.debug(f"  T > {entry} {s} = {x}")
                if x == 0: return 0
            return f'entry {entry} does not match any options in schema'
        elif type(sch) is str:
            if type(entry) is str:
                return f'string `{entry}` != `{sch}`' if entry != sch else 0
            else:
                return f'entry `{entry}` is not a string'
        elif sch is None:
            if entry is None: return 0
            return f'entry `{entry}` is not None'
        elif sch in (str, bool, int, float, list, dict):
            if type(entry) is sch: return 0
            return f'entry `{entry}` is not a {sch}'
        elif type(sch) is list:
            if not type(entry) is list: return f'entry `{entry}` is not a list'
            if   len(sch) == 0:
                 return 0
            elif len(sch) == 1:
                for entid,ent in enumerate(entry):
                    x = check_an_enry(ent,sch[0])
                    if x != 0:
                        return f'list entry #{entid} returns error: {x}'
                return 0
            elif len(sch) != len(entry):
                return f'size of {sch} and {entry} are not the same'
            else:
                for entid,(s,e) in enumerate(zip(sch,entry)):
                    x = check_an_enry(e,s)
                    if x != 0:
                        return f'list entry #{entid} returns error: {x}'
                return 0
        elif type(sch) is dict:
            if not type(entry) is dict: return f'entry `{entry}` is not a dictionary'
            reqnames = [ x[1:] for x in sch if x[0] == '*' ]
            optnames = [ x[1:] for x in sch if x[0] == '>' ]
            allnames = [ x[1:] for x in sch                ]
            for n in reqnames:
                if not n in entry:
                    return f'key `{n}` is missing in entry `{entry}`'
                x = check_an_enry(entry[n],sch['*'+n])
                if x != 0:
                    return f'dictionary entry {n} returns error: {x}'
            for n in optnames:
                if not n in entry: continue
                x = check_an_enry(entry[n],sch['>'+n])
                if x != 0:
                    return f'dictionary entry {n} returns error: {x}'
            for n in entry:
                if not n in allnames:
                    return f'unknown entry `{n}` for a dictionary'
            return 0
        else:
            return f'we should be here! {entry}, {sch}'
        
    logger = logging.getLogger( 'job_steps_sanity_check' )
    steps = config['job_steps']
    for sid,s in enumerate(steps):
        stepfn = s[ 'function' ]
        stepid = s['identifier']
        if not stepid in config:
            continue
        stepsm = STEP_PARAMETERS[ stepfn ]
        steppr = config[stepid]
        x = check_an_enry(steppr,stepsm)
        if x !=0:
            logger.error(f'step #{sid+1} return an error {x}')
            raise RuntimeError(f'step #{sid+1} return an error {x}')
    return 0
        # print(stepsm,steppr)
    
if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s:%(name)-33s:%(lineno)-6d%(levelname)-8s:%(message)s', \
        level="DEBUG" )

    with open(sys.argv[1]) as fd:
        j = json.load(fd)
    
    print( job_sanity(j) )
    print( job_steps_sanity(j) )
    print( steps_sanity(j) )
        
        
    

