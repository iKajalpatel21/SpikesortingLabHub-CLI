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

try:
    from .__sanitizer import STEP_PARAMETERS,step_sanity,sanitize_preprocessing,sanitize_sorting,sanitize_analyzer
except:
    from __sanitizer import STEP_PARAMETERS,step_sanity,sanitize_preprocessing,sanitize_sorting,sanitize_analyzer

"""
These are main functions for both CLI until `runthepipe` and SpikesortingLabHub worker.
In both cases a spikesorting job is a sequence of steps. Each step is a single function call.
Each step has an identifier which used for:
- find parameters in configuration for the current step, i.e. parameters of the step are 
  the value of an identifier key in job dictionary
- identify the step result saved in the carrier (see below)
- identify which results computed by previous steps should be used for the current step, listed in dependencies

The job execution is a linear algorithm:
- create empty carrier dictionary
- call fist step function with config and carrier
  - the function compute results and returns carrier with additional entrance
    `identify:step_results`
- call nest step with new carrier
- continue until the last step


Each step function has the same arguments:
|   Argument   |    Type     | Meaning                                                         |
|:------------:|:-----------:|:----------------------------------------------------------------|
|   `config`   |    dict     | An entire configuration for the spikesorting job                |
| `identifier` |     str     | The identifier of current job step.                             |
|`dependencies`|list or tuple| Identifiers on which step depends                               |
|  `carrier`   |    dict     | Results of the previous steps                                   |
"""

def combined_recording(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    
    Combines several binary files in a one and creates a recording, then sets probe configuration, used channels, and bad channels.
    
    """
    logger = logging.getLogger( config['job_id']+':'+identifier )


    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError(f'Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'combined_recording',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration for `combined_recording`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration for `combined_recording`: {x}')

    recconf = config[identifier]

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    
    try:
        import spikeinterface.full as si
        from probeinterface import read_probeinterface
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    try:
        si.set_global_job_kwargs(**set_si_kwargs(config))
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
        

    buffersize = 4096
    try:
        with open(recconf['combined file'],'wb') as outfd:
            for infile in recconf['input files']:
                with open(infile,'rb') as infd:
                    while True:
                        xbf = infd.read(buffersize)
                        if not xbf : break
                        outfd.write(xbf)
    except BaseException as e:
        logger.error(f'Cannot combined files into one: {e}')
        raise RuntimeError(f'Cannot combined files into one: {e}')

    logger.info('Files merged')
    rec_scales = {}
    if 'gain_to_uV' in recconf:
        rec_scales['gain_to_uV'] = recconf['gain_to_uV']
        rec_scales['offset_to_uV'] = 0.0
    if 'offset_to_uV' in recconf:
        rec_scales['offset_to_uV'] = recconf['offset_to_uV']
    if not os.path.isfile(recconf['binfile']):
        if 'location' in recconf:
            logger.warning('File {} does not exist, trying to read original source {}'.format(recconf['binfile'],recconf['location']))
            recconf['binfile'] = recconf['location']
            if not os.path.isfile(recconf['binfile']):
                logger.error('File {} does not exist'.format(recconf['binfile']))
                raise RuntimeError('Both binary file {} and source recording do not exist'.format(recconf['binfile'],recconf['location']))
            logger.info("=== USING FILE from the original source ===")
        else:
            logger.error('File {} does not exist, but location of the original source not given'.format(recconf['binfile']))
            raise RuntimeError('File {} does not exist, but location of the original source not given'.format(recconf['binfile']))
    
    for reqvar in ('probe','sampling rate','number of channels'):
        if not reqvar in recconf:
            logger.error(f'cannot find `{reqvar}` in thre recording configuration {identifier}')
            raise RuntimeError(f'cannot find `{reqvar}` in thre recording configuration {identifier}')
            
    while len(recconf['probe']) != 0 and not os.path.isfile(recconf['probe']):
        recconf['probe'] = '/'.join(recconf['probe'].split('/')[1:])
    if len(recconf['probe']) == 0:
        logger.error('Probe file cannot be found')
        raise RuntimeError('Probe file cannot be found')
        
    recording = si.BinaryRecordingExtractor(
        recconf['combined file'],recconf['sampling rate'],
        'int16', num_channels=recconf['number of channels'],
        **rec_scales )
    
    if     "remove" in recconf\
      and type(recconf["remove"]) is list\
      and  len(recconf["remove"]) > 0:
        recording = recording.remove_channels(recconf["remove"])

    prob = read_probeinterface(recconf['probe']).probes[0]
    recording.set_probe(prob,in_place=True)
    
    if      "bad_channels" in recconf \
        and type(recconf["bad_channels"]) is list\
        and  len(recconf["bad_channels"]) > 0:
        recording = recording.remove_channels(recconf["bad_channels"])
    
    if "save" in recconf:
        savefile = recconf["save"] if type(recconf["save"]) is str else \
            ( (os.path.splitext(recconf['combined file'])[0]+'.json') if recconf["save"] else None )
        if not savefile is None:
            recconf['binfile'] = recconf['combined file']
            del recconf['input files'], recconf['combined file']
            try:
                with open(savefile,'w') as fd:
                    json.dump(recconf, fd, indent=4)
            except BaseException as e:
                logger.warning(f'Cannot save recording configuration into {savefile}: {e}')

    logger.infor('Combined recording is created')
    carrier[identifier] = recording
    return carrier
    
def __create_recording(recconf:dict):
    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    
    try:
        import spikeinterface.full as si
        from probeinterface import read_probeinterface
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    if   'binfile' in recconf:
        rec_scales = {}
        if 'gain_to_uV' in recconf:
            rec_scales['gain_to_uV'] = recconf['gain_to_uV']
            rec_scales['offset_to_uV'] = 0.0
        if 'offset_to_uV' in recconf:
            rec_scales['offset_to_uV'] = recconf['offset_to_uV']
        if not os.path.isfile(recconf['binfile']):
            if 'location' in recconf:
                logger.warning('File {} does not exist, trying to read original source {}'.format(recconf['binfile'],recconf['location']))
                recconf['binfile'] = recconf['location']
                if not os.path.isfile(recconf['binfile']):
                    logger.error('File {} does not exist'.format(recconf['binfile']))
                    raise RuntimeError('Both binary file {} and source recording do not exist'.format(recconf['binfile'],recconf['location']))
                logger.info("=== USING FILE from the original source ===")
            else:
                logger.error('File {} does not exist, but location of the original source not given'.format(recconf['binfile']))
                raise RuntimeError('File {} does not exist, but location of the original source not given'.format(recconf['binfile']))
        
        for reqvar in ('probe','sampling rate','number of channels'):
            if not reqvar in recconf:
                logger.error(f'cannot find `{reqvar}` in thre recording configuration {identifier}')
                raise RuntimeError(f'cannot find `{reqvar}` in thre recording configuration {identifier}')
                
        while len(recconf['probe']) != 0 and not os.path.isfile(recconf['probe']):
            recconf['probe'] = '/'.join(recconf['probe'].split('/')[1:])
        if len(recconf['probe']) == 0:
            logger.error('Probe file cannot be found')
            raise RuntimeError('Probe file cannot be found')
            
        recording = si.BinaryRecordingExtractor(
            recconf['binfile'],recconf['sampling rate'],
            'int16', num_channels=recconf['number of channels'],
            **rec_scales )
        if     "remove" in recconf\
          and type(recconf["remove"]) is list\
          and  len(recconf["remove"]) > 0:
            recording = recording.remove_channels(recconf["remove"])
    elif 'neuralynx' in recconf:
        recording = si.read_neuralynx(recconf['neuralynx'])
    prob = read_probeinterface(recconf['probe']).probes[0]
    recording.set_probe(prob,in_place=True)
    if      "bad_channels" in recconf \
        and type(recconf["bad_channels"]) is list\
        and  len(recconf["bad_channels"]) > 0:
        recording = recording.remove_channels(recconf["bad_channels"])

    if "save" in recconf:
        savefile = recconf["save"] if type(recconf["save"]) is str else \
            ( (os.path.splitext(recconf['binfile'] if 'binfile' in recconf else recconf['neuralynx'])[0]+'.json') \
                if recconf["save"] else None )
        if not savefile is None:
            try:
                with open(savefile,'w') as fd:
                    json.dump(recconf, fd, indent=4)
            except BaseException as e:
                logger.warning(f'Cannot save recording configuration into {savefile}: {e}')

    return recording
    
def recording(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Reads a recording, sets probe configuration, used channels, and bad channels.
    
    """
    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError(f'Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'recording',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration for `recording`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration for `recording`: {x}')


    recconf = config[identifier]
    
    recording = __create_recording(recconf)
    
    logger.infor('Recording is created')

    carrier[identifier] = recording
    return carrier

    
def load_recording(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Load recording configurations and creates the recording.
    
    """
    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError(f'Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'load_recording',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration for `recording`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration for `recording`: {x}')

    loadrecconf = config[identifier]
    try:
        with open(loadrecconf['file']) as fd:
            recconf = json.load(fd)
    except BaseException as e:
        logger.error('Cannot load recoding configuration from `{}`: {}'.format(loadrecconf['file'],e))
        raise RuntimeError('Cannot load recoding configuration from `{}`: {}'.format(loadrecconf['file'],e))
    recconf['save'] = False
    
    recording = __create_recording(recconf)
    
    logger.infor('Recording is loaded')

    carrier[identifier] = recording
    return carrier
    
def preprocessing(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Creates preprocessing pipeline, runs it, and 
        saves the preprocessed result on disk
    Returns updated carrier.
    Configuration for preprocessing must have `methods` entrance and must be a list
    of applied procedures. It can be empty for no preprocseccing.
    Each procedure may have dictionary with parameters.
    If there is `folder` key in configuration, this name will be used as folder name
    instead of identifier to store preprocessed data on disk.
    """
    def resolvepreproc(si, logger, cmd:str,rec,config:(dict,None)):
        """
        plugs requested preprocessing into the pipline
        returns the tail of pipeline
        """
        if   cmd == 'centering':
            return si.center(rec)\
                if config is None else\
                   si.center(rec,**config)
        elif cmd == 'highpass or band filtering':
            return si.filter(rec)\
                if config is None else\
                   si.filter(rec,**config)
        elif cmd == 'referensing':
            return si.common_reference(rec)\
                if config is None else\
                   si.common_reference(rec,**config)
        elif cmd == 'whitening':
            return si.whiten(rec)
        elif cmd == 'zscore':
            return si.zscore(rec)\
                if config is None else\
                   si.zscore(rec,**config)
        else:
            logger.error(f'Unnknown perprocessing option{cmd}')
            raise RuntimeError(f'Unnknown perprocessing option{cmd}')

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'preprocessing',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')

    x = sanitize_preprocessing(config, identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')

    preprocconf = config[identifier]

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
    
    preproc = [ carrier[ dependencies[0] ] ]
    for ppm in preprocconf['methods']:
        logger.info(f" > PREPROCs: {ppm}")
        pp_config = preprocconf[ppm] if ppm in preprocconf else None
        try:
            preproc.append( resolvepreproc(si,logger, ppm, preproc[-1],pp_config) )
        except BaseException as e:
            logger.error(f'Cannot perform {ppm} in `{identifier}` section: {e}')
            raise RuntimeError(f'Cannot perform {ppm} in `{identifier}` section: {e}')

    preproc[-1].annotate(is_filtered=True)

    preproc_saved = preproc[-1].save(
        folder = config['job_evn']['base directory']+'/'+(preprocconf['folder'] if 'folder' in preprocconf else identifier), 
        chunk_duration = si.get_global_job_kwargs()['chunk_duration'],
        overwrite=True
        )
    carrier[identifier] = preproc_saved
    logger.info(f' > Preprocessing `{identifier}` is done')
    return carrier

def load_preprocessing(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'load_preprocessing',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `load_preprocessing`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `load_preprocessing`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
    
    preprocdir = config[identifier]['folder']
    try:
        preproc = si.load_extractor(preprocdir)
    except BaseException as e:
        logger.error(f'Cannot read preprocessing from the folder {preprocdir}: {e}')
        raise RuntimeError(f'Cannot read preprocessing from the folder {preprocdir}: {e}')
    carrier[identifier] = preproc
    logger.info(f' > Preprocessing `{identifier}` was loaded from the directory {preprocdir}')
    return carrier
    
def sorting(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Creates and runs sorting, 
       saves results in a directory, and cleans working directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'sorting',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `sorting`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `sorting`: {x}')

    x = sanitize_sorting(config,identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `sorting`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `sorting`: {x}')

    sortconf = config[identifier]
    if not type(sortconf) is dict:
        logger.error(f'incorrect type of the `{identifier}` entrance: got {type(sortconf)} but should be a dictionary')
        raise RuntimeError(f'incorrect type of the `{identifier}` entrance: got {type(sortconf)} but should be a dictionary')
    
    
    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
    
    preproc = carrier[ dependencies[0] ]
        
    
    if not 'parameters' in sortconf:
        sortconf['parameters'] = {}
        logger.warning("Cannot find sorter parameters - use default!")

    default_parameters = si.get_default_sorter_params( sortconf['name'] )
    if 'job_kwargs' in config['job_evn'] and 'job_kwargs' in default_parameters:
        sortconf['parameters']["job_kwargs"] = config['job_evn']['job_kwargs']
    else:
        def setadict(d:dict,prm:str,val):
            for n in d:
                if n == prm:
                    d[n] = val
                elif type(d[n]) is dict:
                    d[n] = setadict(d[n],prm,val)
            return d
        sudict = {
                "n_jobs": config['job_evn']['job_kwargs']["n_jobs"],
                "total_memory": config['job_evn']['job_kwargs']["total_memory"],
                "progress_bar": True,
                "verbose" : True,
                "useGPU" : True,
                "overwrite" : True,
                "num_workers" : config['job_evn']['job_kwargs']["n_jobs"],
                "n_processors" : config['job_evn']['job_kwargs']["n_jobs"],
                "n_gpu_processors" : 1,
                "multi_processing" : True,
                "core_dist_n_jobs" : config['job_evn']['job_kwargs']["n_jobs"],
                "clustering_n_jobs" : config['job_evn']['job_kwargs']["n_jobs"],
            }
        for n in sudict:
            sortconf['parameters'] = \
                setadict(
                    sortconf['parameters'],
                    n,
                    sudict[n]
                )
    #DB>>
    logger.debug(f"    > configuration = {json.dumps(sortconf,indent=4)}")
    #<<DB
    srdir = config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir"
    if os.path.isdir(srdir): delosdir(srdir)
    svdir = config['job_evn']['base directory']+'/'+(sortconf['folder'] if 'folder' in sortconf else identifier)
    
    logger.info(f" > SORTING: "+sortconf['name'])
    logger.info(f"    > working directory     = {srdir}")
    logger.info(f"    > destination directory = {svdir}")
    
    if 'image' in sortconf:
        logger.info(f'    > Container : '+sortconf['image'])
        conimage = sortconf['image']
        if sys.platform == 'linux':
            try:
                sorting = si.run_sorter(
                    sorter_name=sortconf['name'],
                    recording=preproc, 
                    folder=srdir,
                    singularity_image = conimage,
                    **sortconf['parameters'] )
            except BaseException as e:
                if os.path.isfile(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                    shutil.copy(
                        getospath(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                        getospath(config['job_evn']['base directory']+f"/{identifier}-spikeinterface_sorter_log.json")
                    )
                logger.error(f"Sorting failed: {e}")
                raise RuntimeError(f"Sorting failed: {e}")
        elif sys.platform == 'win32' or sys.platform == 'win64':
            dockerpath = os.path.basename(conimage)
            dockerpath,_ = os.path.splitext(dockerpath)
            try:
                sorting = si.run_sorter(
                    sorter_name=sortconf['name'],
                    recording=preproc, 
                    folder=srdir,
                    docker_image=f"spikeinterface/{dockerpath}",
                    **sortconf['parameters'] )
            except BaseException as e:
                if os.path.isfile(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                    shutil.copy(
                        getospath(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                        getospath(config['job_evn']['base directory']+f"/{identifier}-spikeinterface_sorter_log.json")
                    )
                logger.error(f"    > Sorting failed: {e}")
                raise RuntimeError(f"Sorting failed: {e}")
        else:
            logger.error(f"    > Sorting failed: unknow platform")
            raise RuntimeError(f"Sorting failed: unknow platform")
    else:
        try:
            sorting = si.run_sorter(
                sorter_name=sortconf['name'],
                recording=preproc, 
                folder=srdir,
                **sortconf['parameters'] )
        except BaseException as e:
            if os.path.isfile(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                shutil.copy(
                    getospath(config['job_evn']['base directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                    getospath(config['job_evn']['base directory']+f"/{identifier}-spikeinterface_sorter_log.json")
                )
            logger.error(f"    > Sorting failed: {e}")
            raise RuntimeError(f"Sorting failed: {e}")

    sorting_saved = sorting.save(folder=svdir,overwrite=True)
    carrier[identifier] = sorting_saved
    logger.info(f"    > Sorting saved")

    # if "save working dir" in last and type(last["save working dir"]) is bool and last["save working dir"]:
        # return carrier    
    delosdir(f'{srdir}')
    return carrier


def load_sorting(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Loads sorting from a folder
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'load_sorting',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `load_sorting`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `load_sorting`: {x}')
        
    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    sortdir = config[identifier]['folder']
    try:
        sorting = si.load_extractor(sortdir)
    except BaseException as e:
        logger.error(f'Cannot read sorting from the folder {sortdir}: {e}')
        raise RuntimeError(f'Cannot read sorting from the folder {sortdir}: {e}')
    carrier[identifier] = sorting
    logger.info(f'    > sorting `{identifier}` was loaded from the directory {sortdir}')
    return carrier
        
    
def analyzer(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Creates and runs analyzer, 
       saves results in a directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'analyzer',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `analyzer`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `analyzer`: {x}')

    x = sanitize_analyzer(config,identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `analyzer`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `analyzer`: {x}')

    analyzeconf = config[identifier]
    
    
    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    logger.info(f" > ANALYZER:")    
    analyzedir = config['job_evn']['base directory'] + '/' + (analyzeconf['folder'] if 'folder' in analyzeconf else identifier)
    logger.info(f"    > folder : {analyzedir}")
    recording  = carrier[ dependencies[0] ]
    sorting    = carrier[ dependencies[1] ]
    try:    
        analyzer = si.create_sorting_analyzer(
            recording=recording,
            sorting=sorting,
            folder=analyzedir,
            format="binary_folder",
            overwrite=True
            )
    except BaseException as e:
        logger.error(f"Cannot create an analyser: {e}")
        raise RuntimeError(f"Cannot create an analyser: {e}")
    if not 'metrics' in analyzeconf:
        logger.warning('analyzer section exist bu does not have metrics to compute')
        raise RuntimeWarning('analyzer section exist bu does not have metrics to compute')
    def recursive_extensions(analyzer,mm:str):
        ext = si.sortinganalyzer.get_extension_class(mm)
        for dep in ext.depend_on:
            for x in dep.split('|'):
                if not analyzer.has_extension(x):
                    recursive_extensions(analyzer,x)
                    analyzer.compute(input=x)
                    logger.warning(f'For metric {mm} computed extension {dep} with default parameters')
        
    def move_at_front(l:list,mm:str):
        logger.debug(f'   >  list:{l} mm:{mm}')
        mmid = l.index(mm)
        ext = [
            x for dep in si.sortinganalyzer.get_extension_class(mm).depend_on \
              for x in dep.split('|')
        ]
        logger.debug(f'    >  ext :{ext}')
        for x in ext:
            if not x in l[:mmid]:
                if x in l:
                    l.remove(x)
                    l = l[:mmid]+[x]+l[mmid:]
                    l = move_at_front(l,x)
                else:
                    l = [x]+l
        return l

    logger.debug(f'    > putting metrics in right order')
    #logger.debug(f'   > '+ analyzeconf['metrics'])
    metrics = [ mm for mm in analyzeconf['metrics'] ]
    logger.debug(f'    > Metrics before sotring {metrics}')
    logger.info(f'    > Processing metrics: {metrics}')
    for mm in analyzeconf['metrics']:
        if not mm in si.get_available_analyzer_extensions():
            logger.error(f"An requested metric {mm} is not valid metric. Valid metric are {si.get_available_analyzer_extensions()}")
            raise RuntimeError(f"An requested metric {mm} is not valid metric. Valid metric are {si.get_available_analyzer_extensions()}")
        metrics = move_at_front(metrics, mm)
    logger.debug(f'    > Computing metrics: {metrics}')
    analyzer.compute(input=metrics, extension_params=analyzeconf['metrics'])
    logger.info(f'    > Analysise of {metrics} complite!')
    carrier[identifier] = analyzer
    logger.info(f'    > Analysise is finished')
    return carrier

def load_analyzer(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Load analyzer and all extensions from a directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'load_analyzer',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `load_analyzer`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `load_analyzer`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    analyzerdir = config[identifier]['folder']
    try:
        analyzer = si.load_sorting_analyzer(analyzerdir)
    except BaseException as e:
        logger.error(f'Cannot laod  analyzer from the folder {analyzerdir}: {e}')
        raise RuntimeError(f'Cannot laod analyzer from the folder {analyzerdir}: {e}')
    carrier[identifier] = analyzer
    logger.info(f'    > analyzer `{identifier}` was loaded from the directory {analyzerdir}')
    return carrier

def phy_export(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Exports sorting into phy
    carrier is updated with phy directory name.
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'phy_export',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `phy_export`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `phy_export`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        from spikeinterface.exporters import export_to_phy
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    preproc = carrier[ dependencies[0] ]
    sorting = carrier[ dependencies[1] ]

    logger.info(f"EXPORTING PHY")
    phydir = config['job_evn']['base directory']+'/'+ ( config[identifier]['folder'] if 'folder' in config[identifier] else 'phy')
    logger.info(f" > phy directory = {phydir}")
    try:
        pyan = si.create_sorting_analyzer(
            recording=preproc,
            sorting=sorting)
    except BaseException as e:
        logger.error(f"Cannot create an analyzer for phy exporting `{identifier}`: {e}")
        raise RuntimeError(f"Cannot create an analyzer for phy exporting `{identifier}`: {e}")
            
    try:
        pyan.compute(['random_spikes', 'waveforms', 'templates', 'noise_levels'])
        _ = pyan.compute('spike_amplitudes')
        _ = pyan.compute('principal_components', n_components = 5, mode="by_channel_local")
    except BaseException as e:
        logger.error(f"Cannot analyzer sorting for phy exporting `{identifier}`: {e}")
        raise RuntimeError(f"Cannot analyzer sorting for phy exporting `{identifier}`: {e}")
    
    try:
        export_to_phy(
            sorting_analyzer = pyan,
            remove_if_exists = True,
            output_folder    = phydir
        )
    except BaseException as e:
        logger.error(f"Cannot export to phy: {e}")
        raise RuntimeError(f"Cannot export to phy: {e}")        
    carrier[identifier] = phydir

    
    if 'do_not_update_config' in config[identifier] and config[identifier]['do_not_update_config']:
        logger.warning(" > Skipping folder optimization ")
        return carrier
        
    import hashlib, re
    def checksum(filename, chunk_num_blocks=8192):
        h = hashlib.md5()
        with open(filename,'rb') as f: 
            while chunk := f.read(chunk_num_blocks*h.block_size): 
                h.update(chunk)
        return h.hexdigest()

    
    logger.info(" > Computing Check Sums - please wait a bit, it may take quite a while")    
    ppfile = config['job_evn']['base directory']+'/'+ (config[dependencies[0]]['folder'] if 'folder' in config[dependencies[0]] else dependencies[0])+'/traces_cached_seg0.raw'
    phfile = phydir+'/recording.dat'
    phconf = phydir+'/params.py'
    if not os.path.isfile(phfile): 
        logger.error(f"phy exporting `{identifier}` can't optimized phy directory: `{phfile}` not found")
        raise RuntimeError(f"phy exporting `{identifier}` can't optimized phy directory: `{phfile}` not found")
        
    if not os.path.isfile(phconf):
        logger.error(f"phy exporting `{identifier}` can't optimized phy directory: `{phconf}` not found")
        raise RuntimeError(f"phy exporting `{identifier}` can't optimized phy directory: `{phconf}` not found")
        
    pphash = checksum(ppfile) if os.path.isfile(ppfile) else ''
    logger.info(f"    > {pphash}")
    phhash = checksum(phfile)
    logger.info(f"    > {phhash}")
    phy_config = open(phconf).read()
    if pphash == phhash:
        logger.info(" > The both files are identical! Removing phy file")
        os.remove(phfile)
        phy_config = re.sub(r'dat_path .*\n',f'dat_path = "../'+(config[dependencies[0]]['folder'] if 'folder' in config[dependencies[0]] else dependencies[0])+'/traces_cached_seg0.raw"\n',phy_config)
    else:
        logger.info(" > The files are different - leaving both")
        phy_config = re.sub(r'dat_path .*\n',f'dat_path = "recording.dat"\n',phy_config)
    logger.info(" > Updating PHY")
    with open(phconf,'w') as fd:
        fd.write(phy_config)
    logger.info(f" > exported to {phydir} is finished")
    return carrier


def import_from_phy(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Imports from phy directory
        carrier is updated with new sorting object.
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'import_from_phy',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `import_from_phy`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `import_from_phy`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        import spikeinterface.extractors as se
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
    

    logger.info(f"IMPORTING SORTING FROM PHY")
   
    sortingdir  = config['job_evn']['base directory'] + '/' + (config[identifier]['folder'] if 'folder' in config[identifier] else identifier)
    phydir      = config[identifier]['phy_folder']
    try:
        sorting       = se.read_phy(phydir)
        sorting_saved = sorting.save(
            folder    = sortingdir,
            overwrite = True)
    except BaseException as e:
        logger.error(f'Cannot import from phy: {e}')
        raise RuntimeError(f'Cannot import from phy: {e}')

    carrier[identifier] = sorting_saved
    logger.info(f" > imported sorter from {phydir}")
    return carrier

def report(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Generated images and other statistical data out of analyzer
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )
    
    logger.info('SAVING REPORT')
    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'report',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `report`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `report`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        from spikeinterface.exporters import export_report
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')
    
    analyzer  = carrier[ dependencies[0] ]
    reportdir = config['job_evn']['base directory']+'/'+ (config[identifier]['folder'] if 'folder' in config[identifier] else identifier)
    try:
        export_report(
            sorting_analyzer=analyzer, 
            output_folder=reportdir
        )
    except BaseException as e:
        logger.error(f"Cannot export a report: {e}")
        raise RuntimeError(f"Cannot export a report: {e}")
    carrier[identifier] = reportdir
    logger.info(f' > report is exported to {reportdir}')
    return carrier

def export2matlab(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Exports h5 file for matlab analyses.
        Updates carrier with h5 filename
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )
    
    logger.info('Exporting to MatLab')
    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'export2matlab',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `export2matlab`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `export2matlab`: {x}')

    if 'envs' in config['job_evn']:
        if type(config['job_evn']['envs']) is dict:
            for ev in config['job_evn']['envs']:
                os.environ[ev] = config['job_evn']['envs'][ev]
        else:
            logger.warning('Cannot set environment variables: job_evn/envs is not a dictionary')
    try:
        import spikeinterface.full as si
        si.set_global_job_kwargs(
            **set_si_kwargs(si,config)
        )
    except ImportError:
        logger.error(f'`spikeinterfce[full]` must be installed to run job steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run job steps')
    except BaseException as e:
        logger.error(f'Cannot setup `spikeinterface` kwargs :{e}')
        raise RuntimeError(f'Cannot setup `spikeinterface` kwargs :{e}')

    try:
        import h5py
        import csv
        import numpy as np
    except:
        logger.error(f'`h5py` must be installed to run matlab exporting')
        raise RuntimeError(f'`h5py` must be installed to run matlab exporting')

    reconfig  =  config[ dependencies[0] ]
    sorting   = carrier[ dependencies[1] ]
    analyzer  = carrier[ dependencies[2] ]
    depfun    = get_dep_step(config, dependencies[3])
    
    if    depfun == "phy_export":
        phydir = config['job_evn']['base directory']+'/'+ ( config[identifier]['folder'] if 'folder' in config[dependencies[3]] else 'phy')
    elif  depfun == "import_from_phy":
        phydir = config[ dependencies[3] ]['phy_folder']
    else:
        logger.error(f'The third dependence `{dependencies[2]}` is not phy_export or import_from_phy. In theory we should be here (-.-)')
        raise RuntimeError(f'The third dependence `{dependencies[2]}` is not phy_export or import_from_phy. In theory we should be here (-.-)')

    logger.info(f"Exporting to MatLab:")
    phyids = []
    phygrp = []
    
    if os.path.isfile(f'{phydir}/cluster_info.tsv'):
        with open(f'{phydir}/cluster_info.tsv') as fd:
            reader = csv.DictReader(fd, delimiter="\t")
            for r in reader:
                phyids.append(r['id'])
                phygrp.append(r['group'])

        phyids = array([ int(x) for x in phyids])

    chpos = np.array([])
    if os.path.isfile(f'{phydir}/channel_positions.npy'):
        chpos = np.load(f'{phydir}/channel_positions.npy')
    
    spikes = sorting.to_spike_vector()
    if isinstance(spikes, ndarray):
        spikes = array([
            [x,y]
            for x,y,z in spikes ],dtype=int)
    tpl = analyzer.get_extension("templates")
    spa = analyzer.get_extension("spike_amplitudes").get_data()
    spl = analyzer.get_extension("spike_locations").get_data()
    spl = array([ [x,y] for x,y in zip(spl['x'],spl['y']) ]) 
    unl = analyzer.get_extension("unit_locations").get_data()
    ewf = analyzer.get_extension("waveforms")
  
    unit_ids = sorting.unit_ids
    used_sparsity = analyzer.sparsity
    sparse_dict   = used_sparsity.unit_id_to_channel_indices
    max_num_channels = max(len(chan_inds) for chan_inds in sparse_dict.values())
    dense_templates = tpl.get_templates(unit_ids=unit_ids, operator="average")
    num_samples = dense_templates.shape[1]
    templates = zeros((len(unit_ids), num_samples, max_num_channels), dtype="float64")
    templates_ind = -ones((len(unit_ids), max_num_channels), dtype="int64")
    for unit_ind, unit_id in enumerate(unit_ids):
        chan_inds = sparse_dict[unit_id]
        template = dense_templates[unit_ind][:, chan_inds]
        templates[unit_ind, :, :][:, : len(chan_inds)] = template
        templates_ind[unit_ind, : len(chan_inds)] = chan_inds
            
    u_sample_shapes = array([ ewf.get_waveforms_one_unit(unit_id).shape for unit_id in unit_ids ],dtype=int)

    max_u_samples  = amax(u_sample_shapes[:,0])
    max_u_channels = amax(u_sample_shapes[:,2])
    if unique(u_sample_shapes[:,1]).shape[0] != 1:
        logger.error("There are different shapes in column 1 of samples")
        for u in u_sample_shapes:
            logger.error(f' > {u}')
        raise RuntimeError(f"There are different shapes in column 1 of samples")
    usw = zeros((unit_ids.shape[0],max_u_samples,u_sample_shapes[0,1],max_u_channels))


    usw_d = []
    for unit_ind, unit_id in enumerate(unit_ids):
        wfs = ewf.get_waveforms_one_unit(unit_id)
        usw[unit_ind,:wfs.shape[0],:,:wfs.shape[2]] = wfs
        usw_d.append( list(wfs.shape) )

    actchids = [ i for i in range(reconfig["number of channels"]) ]
    inactive_channels =\
        ( reconfig[   'remove'   ] if    'remove'    in reconfig else [] )+\
        ( reconfig['bad_channels'] if 'bad_channels' in reconfig else [] )
    for b in inactive_channels:
        if b in actchids: actchids.remove(b)
    actchids = array(actchids+[-1],dtype=int)
    templates_indx = copy(templates_ind)
    templates_ind = array([
        actchids[x] for x in templates_indx
    ])
    unit_channel_corrected = True
    
    
    
    if 'marks' in config[identifier] :
        marks = config[identifier]['marks']
    else:
        marks = 'good mua noise unsorted undecided'.split()

    outfile = config['job_evn']['base directory']+'/'+ (config[identifier]['filename'] if 'filename' in config[identifier] else 'spikesorting-export.h5')
    with h5py.File(f'{outfile}', 'w') as hd:
        hd.create_dataset('spikes_time'           , data=spikes[:,0]/sorting._sampling_frequency )
        hd.create_dataset('spikes_unit'           , data=spikes[:,1] )
        hd.create_dataset('spike_amplitudes'      , data=spa )
        hd.create_dataset('spike_locations'       , data=spl )
        hd.create_dataset('unit_location'         , data=unl)
        hd.create_dataset('unit_waveform'         , data=templates)
        hd.create_dataset('unit_channels'         , data=templates_ind)
        hd.create_dataset('unit_channel_corrected', data=unit_channel_corrected)
        hd.create_dataset('unit_samples_waveform' , data=usw)
        hd.create_dataset('unit_samples_sizes'    , data=array(usw_d))
        hd.create_dataset('phy_ids'               , data=phyids)
        hd.create_dataset('unit_label'            , data=[ marks.index(x) if x in marks else -1 for x in phygrp] if len(phygrp) != 0 else phygrp)
        hd.create_dataset('phy_channel_position'  , data=chpos )
    carrier[identifier] = outfile
    logger.info(f' > Exported sorting into MatLab file {outfile}')
    return carrier


def upload(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict): 
    """
    Uploads current work directory to the cloud
    Returns unchanged carrier dictionary
    """

    logger = logging.getLogger( config['job_id']+':'+identifier )
    
    logger.info('Uploading Results')
    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'upload',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `upload`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `upload`: {x}')

    import hashlib, time, re, os
    from numpy.random import randint
    
    uploadconfig = config[identifier]

    cpy = uploadconfig["keep_base directory"] if "keep_base directory" in uploadconfig else False
    suf = uploadconfig["suffix"]              if "suffix"              in uploadconfig else False
    if type(suf) is bool:
        suf = f'{randint(0xffff):04d}' if suf else ''
    
    source      = config['job_evn']['base directory']
    destination = uploadconfig['destination']+suf
    try:
        os.makedirs(
            os.path.dirname(destination), 
            exist_ok=True
        )
    except BaseException as e:
        return f'Cannot create destination logging directory `{destination}`: {e}'

    logger.info(' > Copying' if cpy else ' > Moving')
    logger.info(f'    > source      = {source}')
    logger.info(f'    > destination = {destination}')
    if cpy:
        logger.info( '    > Copying .... wait ' )
        shutil.copytree(source, destination)
    else:
        logger.info( '    > Moving  .... wait ' )
        shutil.move(source, destination)
    logger.info( ' > DONE ' )
    logger.info('----------------------------')
    return carrier


###>>> Import recording from phy?
    # chpos = load(last['running directory']+'/phy/channel_positions.npy')

    # if os.path.isdir(prepdir) :
        # recording_saved = si.load_extractor(prepdir)
    # else:
        # probe = Probe(ndim=2, si_units='um')
        # probe.set_contacts(positions=chpos, shapes='square', shape_params={'width':11,'height':11})
        # probe.set_device_channel_indices(arange(chpos.shape[0]))

        # recording = si.BinaryRecordingExtractor(
            # last['running directory']+'/phy/temp_wh.dat',sorting._sampling_frequency,'int16', num_channels=chpos.shape[0],
            # gain_to_uV =  0.1949999928474426, offset_to_uV = 0.0)
        # recording.set_probe(probe,in_place=True)
        # recording.annotate(is_filtered=True)
        # recording_saved = recording.save( folder = prepdir, chunk_duration = '30s')
    # last['analyzer-before-phy-curation'] = pycopy.deepcopy(last['analyzer'])
    # last['sorter-before-phy-curation'  ] = pycopy.deepcopy(last['sorter'  ])
    # last['sorter'] = { 'name' : 'phy-curation', 'phy-curation' : {} }
    # if 'folder' in last['sorter-before-phy-curation'  ]:
        # last['sorter']['folder'] = last['sorter-before-phy-curation'  ]['folder']
    # return last,recording_saved,sorting

###<<<
