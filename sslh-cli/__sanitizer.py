import  os,\
       sys,\
    logging,\
     shutil
import json
from inspect import getsourcefile
import psutil
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
    "load_recording": [],
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
        ("sorting","load_sorting","import_from_phy")
    ],
    # Load a previously done analyzer
    "load_analyzer": [],
    # Exporting to phy: the firs argument is a preprocessing, load_preprocessing, combined_recording OR recording, the second is sorting  OR load_sorting
    "phy_export" : [
        ("recording", "combined_recording", "preprocessing", "load_preprocessing"),
        ("sorting","load_sorting")
    ],
    # Importing from phy needs: the only argument is a preprocessing, load_preprocessing, combined_recording OR recording
    "import_from_phy" : [ ],
    # Report requires: the first argument is a preprocessing, load_preprocessing, combined_recording OR recording, the second is sorting  OR load_sorting, the last is analyzer OR load_analyzer
    "report": [
          ("analyzer","load_analyzer")
    ],
    # Export to MatLab requires sorting OR load_sorting AND analyzer OR load_analyzer
    "export2matlab": [
        ("recording", "combined_recording"),
        ("sorting","load_sorting","import_from_phy"),
        ("analyzer","load_analyzer"),
        ("phy_export","import_from_phy")
    ],
    # Upload whatever was done!
    "upload": [],
}


# The first character of the name defines where it is *required or >optional parameter, however
#    if there is ++ parameter this step may have any number of uncontrolled parameters. 
#
# Value are the acceptable types for the parameter,
# if a value is a tuple - it is a choice.
# if a value is a list with one element - any number of elements are allowed, 
#    otherwise number of elements should be strictly equal to the number of elements in the list.

STEP_PARAMETERS = {
    "combined_recording" : {
        '*input files'        : [ str ],
        '*combined file'      : str,
        '*probe'              : str,
        '*sampling rate'      : (int, float),
        '*number of channels' : int,
        ">remove"             : [ int ],
        ">bad_channels"       : [ int ],
        ">location"           : str,
        ">gain_to_uV"         : (int, float),
        ">offset_to_uV"       : (int, float),
        ">save"               : (bool, str )
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
                ">offset_to_uV"       : (int, float),
                ">save"               : (bool, str )
            },
            {
                '*neuralynx'          : str,
                '*probe'              : str,
                ">bad_channels"       : [ int ],
                ">save"               : (bool, str )
            }
    ),
    "load_recording" : {
        ">file": str,
    },
    "preprocessing": {
        "*methods": [ ("centering", "highpass or band filtering", "referensing", "whitening", "zscore") ] ,
        ">centering" : {
            '>mode': ('median', 'mean')
        }, 
        ">highpass or band filtering" : (
            {
            '*btype' : 'bandpass',
            '*band'  : [float,float]
            },{
            '*btype' : 'highpass',
            '*band'  : float
            }
        ),
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
        ">folder":str
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
        "*metrics" : dict,
        ">folder"  : str,
    },
    "load_analyzer": {
        "*folder"  : str
    },
    "phy_export"   : {
        ">folder"  : str,
        ">do_not_update_config" : bool
    },
    "import_from_phy" : {
        "*phy_folder" : str,
        ">folder"     : str
    },
    "report"       : {
        ">folder"  : str
    },
    "export2matlab": {
        ">filename": str,
        ">marks"   : [ str ]
    },
    "upload"       : {
        "*destination"        : str,
        ">keep_base_directory": bool,
        ">suffix"             : (str, bool)
    }
}

JOB_CONFIG = {
    "*version" : "0.4.1",
    ">si"      : "0.101.0",
    ">job_id"  : str,
    "*job_evn" : {
        "*base directory": str,
        "*job_kwargs"    : {
            ">n_jobs"        : int ,
            ">total_memory"  : str,
            ">chunk_duration": str,
            ">progress_bar"  : bool
        },
        ">log_level"     : str,
        ">REDIRECT" : {
            ">log": str,
            ">out": str,
            ">err": str
        },
        ">envs" : dict
    },
    "*job_steps" : [ {"*function":str, "*identifier":str, "*depends":[str] } ],
    "++" : dict
}
    
def base_check(config)->(int,str):
    if not type(config) is dict:
        return 'Configuration is not a dictionary'
    return check_schema_an_enry(config,JOB_CONFIG)

def job_sanity_check(config:dict)->(int,str):
    x = base_check(config)
    if x != 0:
        return x
    if len(config['job_id']) < 2:
        return f'job_id should be at least 2 characters long.'

            
    if 'envs' in config['job_evn']:
        if not type(config['job_evn']['envs']) is dict:
            return 'The environment variable `envs` has a wrong type {}, but should be a dictionary'.format(type(config['job_evn']['envs']))
            
        for env in config['job_evn']['envs']:
            if not type(config['job_evn']['envs'][env]) is str:
                return f'envs entrance {env} has a wrong type. It should be a string only'
                
    return job_steps_sanity(config)


def job_steps_sanity(config:dict)->(int,str):
    steps = config['job_steps']
    if len(steps) < 1:
        return 'job_steps list is empty'
        
    prev_steps_ids = []
    prev_steps_fun = []
    for sid,s in enumerate(steps):
        if not type(s) is dict:
            return f'step #{sid+1} has a incorrect type {type(s)}, but should be a dictionary'
            
        for required_step_item, item_type in [('function',str), ('identifier',str), ('depends',list) ] :
            if not required_step_item in s:
                return f'required step key `{required_step_item}` is missing in the step #{sid+1}'
                
            if not type(s[required_step_item]) is item_type:
                return f'required step key `{required_step_item}` in the step #{sid+1} has an incorrect type {type(s[required_step_item])} but should be {item_type}'
                
        for itm in s:
            if not itm in 'function identifier depends'.split():
                return f'Unknown entrance {itm} in step #{sid+1}'
                
        if not s['function'] in STEP_DEPENDENCIES:
            return 'Unknown function `'+s['function']+f'` in step #{sid+1}. Should be one of these: '+', '.join([_ for _ in STEP_DEPENDENCIES])
            
        
        if s['identifier'] in prev_steps_ids:
            return 'The identifier `{}` is not unique! Step #{} has the same identifier'.format(s['identifier'], prev_steps_ids.index(s['identifier'])+1) 
            
        allowed_dependencies = STEP_DEPENDENCIES[ s['function'] ]
        if len(allowed_dependencies) != len(s['depends']):
            return 'Too many or Not enough dependencies in step #{}. Needs {} but given {}'.format(sid+1,len(allowed_dependencies),len(s['depends'])) 
            
        for depid,dep in enumerate(s['depends']):
            if not dep in prev_steps_ids:
                return f'There is no previous step with ID{dep} required for current step #{sid+1}' 
                
            reffun = prev_steps_fun[ prev_steps_ids.index(dep) ]
            if type(allowed_dependencies[depid]) is str and allowed_dependencies[depid] == reffun: pass
            elif (type(allowed_dependencies[depid]) is list or type(allowed_dependencies[depid]) is tuple) and reffun in allowed_dependencies[depid]: pass
            else:
                return f'Dependence {dep} for current step #{sid+1} has an incorrect function {reffun} but should be (one of these) `{allowed_dependencies[depid]}`'
                
        stepfn = s[ 'function' ]
        stepid = s['identifier']
        x = step_sanity(config,stepfn,stepid)
        if x !=0 :
            return f'`{stepfn}` parameters {stepid} have inconsistencies: {x}' 
            
        if stepfn == 'sorting':
            try:
                x = sanitize_sorting(config,s['identifier'])
            except BaseException as e:
                logger.warning(f'Cannot sanitize parameters of the step #{sid+a}: {e}')
                continue
            if x != 0:
                return f'sorting parameters {stepid} have inconsistencies: {x}' 
                
        elif stepfn == 'analyzer':
            try:
                x = sanitize_analyzer(config,s['identifier'])
            except BaseException as e:
                logger.warning(f'Cannot sanitize parameters of the step #{sid+a}: {e}')
                continue
            if x != 0:
                return f'analyzer parameters {stepid} have inconsistencies: {x}' 
        elif stepfn == 'preprocessing':
            try:
                x = sanitize_preprocessing(config,s['identifier'])
            except BaseException as e:
                logger.warning(f'Cannot sanitize parameters of the step #{sid+a}: {e}')
                continue
            if x != 0:
                return f'preprocessing parameters {stepid} have inconsistencies: {x}' 
            
        prev_steps_ids.append( stepid )
        prev_steps_fun.append( stepfn )

    return 0

def step_sanity(config:dict, function:str, identifier:str)->(int,str):
    logger = logging.getLogger( 'step_sanity_check' )
    if not identifier in config:
        return f'Cannot find `{identifier}` key in the config'    
    
    stepsm = STEP_PARAMETERS[ function ]
    steppr = config[identifier]
    return check_schema_an_enry(steppr,stepsm)

def sanitize_preprocessing(config:dict,identifier:str)->(int,str):
    methods    = config[identifier]['methods']
    allmethods = [ x[1:] for x in  STEP_PARAMETERS['preprocessing'] if x != "*methods" ]
    for method in methods:
        if not method in allmethods:
            return f"Unknown method `{method}` in preprocessing `{identifier}`"
    return 0

def sanitize_sorting(config:dict,identifier:str)->(int,str):
    try:
        import spikeinterface.full as si
    except:
        return f'Cannot check sorting - spikeinterface is not installed'
    
    sorter     = config[identifier]['name']
    parameters = config[identifier]['parameters']
    if not sorter in si.available_sorters():
        return f'Unknown soter `{sorter}`. Currently can run only {si.available_sorters()}'
        

    #Creating schema    
    defaults = si.get_default_sorter_params(sorter)
    schema = recursive_schema(defaults)
    return check_schema_an_enry(parameters,schema)

def sanitize_analyzer(config:dict,identifier:str)->(int,str):
    try:
        import spikeinterface.full as si
    except:
        return f'Cannot check analyzer - spikeinterface is not installed'
        
    extantions = config[identifier]['metrics']
    avelext    = si.get_available_analyzer_extensions()
    for ext in extantions:
        if not ext in avelext:
            return f'Unknown extension in `{identifier}`. Currently can run only {avelext}'
            
    #Creating schema
    schema = {}
    for ext in avelext:
        defaults = si.get_default_analyzer_extension_params(ext)
        schema[f'>{ext}'] = recursive_schema(defaults,mitigate_none=True)
    
    return check_schema_an_enry(extantions,schema)
    
if __name__ == '__main__':
    # logging.basicConfig(
        # format='%(asctime)s:%(name)-33s:%(lineno)-6d%(levelname)-8s:%(message)s', \
        # level="DEBUG" )

    with open(sys.argv[1]) as fd:
        j = json.load(fd)
    
    print( job_sanity_check(j) )
        
    

