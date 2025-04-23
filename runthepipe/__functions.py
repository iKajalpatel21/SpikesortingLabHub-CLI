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
    from .__sanitizer import STEP_PARAMETERS,step_sanity
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
    logger = logging.getLogger( config['job_id']+identifier )


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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')
    
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
    
    carrier[identifier] = recording
    return carrier
       
def recording(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Reads a recording, sets probe configuration, used channels, and bad channels.
    
    """
    logger = logging.getLogger( config['job_id']+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError(f'Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'recording',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration for `recording`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration for `recording`: {x}')


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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')
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
    def resolvepreproc(si, cmd:str,rec,config:(dict,None)=None,logger):
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

    logger = logging.getLogger( config['job_id'] + identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeError('Cannot find `{identifier}` in the configuration')

    x = step_sanity(config,'preprocessing',identifier)
    if x != 0:
        logger.error(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')
        raise RuntimeError(f'There is inconsistencies in the configuration `{identifier}` for `preprocessing`: {x}')

    x = sanitize_sorting(config, identifier)
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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')
    
        
    # if last['rerun']:
        # delosdir('{running directory}/{folder}'.format(folder=(preprocconf['folder'] if 'folder' in preprocconf else "preprocessed"),**last))

    # if not   'methods' in preprocconf:
        # logger.error(f'There is not a `methods` section in `{identifier}` section')
        # raise RuntimeError(f'There is not a `methods` section in `{identifier}` section')
    # if not type(preprocconf['methods']) is list:
        # logger.error(f'The `methods` section in `{identifier}` section is not a list')
        # raise RuntimeError(f'The `methods` section in `{identifier}` section is not a list')
    # if len(dependencies) != 1:
        # logger.error(f'dependencies must have only one identifier but got {len(dependencies)}')
        # raise RuntimeError(f'dependencies must have only one identifier but got {len(dependencies)}')
    
    preproc = [ carrier[ dependencies[0] ] ]
    for ppm in preprocconf['methods']:
        logger.info(f"PREPROC: {ppm}")
        config = preprocconf[ppm] if ppm in preprocconf else None
        try:
            preproc.append( resolvepreproc(si, ppm, preproc[-1],config,logger) )
        except BaseException as e:
            logger.error(f'Cannot perform {ppm} in `{identifier}` section: {e}')
            raise RuntimeError(f'Cannot perform {ppm} in `{identifier}` section: {e}')

    preproc[-1].annotate(is_filtered=True)
    preproc_saved = preproc[-1].save(
        folder = config['job_evn']['base_directory']+'/'+(preprocconf['folder'] if 'folder' in preprocconf else identifier), 
        chunk_duration = si.get_global_job_kwargs()['chunk_duration']
        )
    carrier[identifier] = preproc_saved
    logger.info(f'Preprocessing `{identifier}` is done')
    return carrier

def load_preprocessing(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')
    
    preprocdir = config[identifier]['folder']
    try:
        preproc = si.load_extractor(preprocdir)
    except BaseException as e:
        logger.error(f'Cannot read preprocessing from the folder {preprocdir}: {e}')
        raise RuntimeError(f'Cannot read preprocessing from the folder {preprocdir}: {e}')
    carrier[identifier] = preproc
    logger.info(f'Preprocessing `{identifier}` was loaded from the directory {preprocdir}')
    return carrier
    
def sorting(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Creates and runs sorting, 
       saves results in a directory, and cleans working directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')



    # if last['rerun']:
        # delosdir('{running directory}/sorting-workingdir'.format(**last))
        # delosdir('{running directory}/sorting-saved'.format(**last))

    # if not 'name' in sortconf:
        # logger.error(f'cannot find `name` in the sorting configuration {identifier}')
        # raise RuntimeError(f'cannot find `name` in the sorting configuration {identifier}')
    # if len(dependencies) != 1:
        # logger.error(f'dependencies must have only one identifier but got {len(dependencies)}')
        # raise RuntimeError(f'dependencies must have only one identifier but got {len(dependencies)}')
    
    preproc = carrier[ dependencies[0] ]
        
    
    if not 'parameters' in sortconf:
        sortconf['parameters'] = {}
        logger.warning("Cannot find sorter parameters - use default!")

    if 'job_kwargs' in config['job_evn']:
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
    logger.debug(f" > configuration = {json.dumps(sortconf,indent=4)}")
    #<<DB
    srdir = config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir"
    logger.info(f"SORTING: "+sortconf['name'])
    if 'image' in sortconf:
        logger.info(f' > Container : '+sortconf['image'])
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
                if os.path.isfile(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                    shutil.copy(
                        getospath(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                        getospath(config['job_evn']['base_directory']+f"/{identifier}-spikeinterface_sorter_log.json")
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
                if os.path.isfile(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                    shutil.copy(
                        getospath(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                        getospath(config['job_evn']['base_directory']+f"/{identifier}-spikeinterface_sorter_log.json")
                    )
                logger.error(f"Sorting failed: {e}")
                raise RuntimeError(f"Sorting failed: {e}")
        else:
            logger.error(f"Sorting failed: unknow platform")
            raise RuntimeError(f"Sorting failed: unknow platform")
    else:
        try:
            sorting = si.run_sorter(
                sorter_name=sortconf['name'],
                recording=preproc, 
                folder=srdir,
                **sortconf['parameters'] )
        except BaseException as e:
            if os.path.isfile(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"):
                shutil.copy(
                    getospath(config['job_evn']['base_directory']+f"/{identifier}-sorting-workingdir/spikeinterface_log.json"),
                    getospath(config['job_evn']['base_directory']+f"/{identifier}-spikeinterface_sorter_log.json")
                )
            logger.error(f"Sorting failed: {e}")
            raise RuntimeError(f"Sorting failed: {e}")

    sorting_saved = sorting.save(folder=config['job_evn']['base_directory']+'/'+(sortconf['folder'] if 'folder' in sortconf else identifier))
    carrier[identifier] = sorting_saved
    logger.info(f"Sorting saved")

    # if "save working dir" in last and type(last["save working dir"]) is bool and last["save working dir"]:
        # return carrier    
    delosdir(f'{srdir}')
    return carrier


def load_sorting(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Loads sorting from a folder
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')
    sortdir = config[identifier]['folder']
    try:
        sorting = si.load_extractor(sortdir)
    except BaseException as e:
        logger.error(f'Cannot read sorting from the folder {sortdir}: {e}')
        raise RuntimeError(f'Cannot read sorting from the folder {sortdir}: {e}')
    carrier[identifier] = sorting
    logger.info(f'sorting `{identifier}` was loaded from the directory {sortdir}')
    return carrier
        
    
def analyzer(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Creates and runs analyzer, 
       saves results in a directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')

    logger.info(f"ANALYZER:")    
    subfolder = analyzeconf['folder'] if 'folder' in analyzeconf else identifier
    logger.info(f" > folder : {subfolder}")
    recording  = carrier[ dependencies[0] ]
    sorting    = carrier[ dependencies[1] ]
    try:    
        analyzer = si.create_sorting_analyzer(
            recording=recording,
            sorting=sorting,
            folder=config['job_evn']['base_directory']+f'/{subfolder}',
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

    logger.debug(f' > putting metrics in right order')
    #logger.debug(f'   > '+ analyzeconf['metrics'])
    metrics = [ mm for mm in analyzeconf['metrics'] ]
    logger.debug(f' > Metrics before sotring {metrics}')
    logger.info(f' > Processing metrics: {metrics}')
    for mm in analyzeconf['metrics']:
        if not mm in si.get_available_analyzer_extensions():
            logger.error(f"An requested metric {mm} is not valid metric. Valid metric are {si.get_available_analyzer_extensions()}")
            raise RuntimeError(f"An requested metric {mm} is not valid metric. Valid metric are {si.get_available_analyzer_extensions()}")
        metrics = move_at_front(metrics, mm)
    logger.debug(f' > Computing metrics: {metrics}')
    analyzer.compute(input=metrics, extension_params=analyzeconf['metrics'])
    logger.info(f' > Analysise of {metrics} complite!')
    carrier[identifier] = analyzer
    logger.info(f"Sorting saved")
    logger.info(f' > Analysise is finished')
    return carrier

def load_analyzer(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Load analyzer and all extensions from a directory
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')

    analyzerdir = config[identifier]['folder']
    try:
        analyzer = si.load_sorting_analyzer(analyzerdir)
    except BaseException as e:
        logger.error(f'Cannot laod  analyzer from the folder {analyzerdir}: {e}')
        raise RuntimeError(f'Cannot laod analyzer from the folder {analyzerdir}: {e}')
    carrier[identifier] = analyzer
    logger.info(f'analyzer `{identifier}` was loaded from the directory {analyzerdir}')
    return carrier

def phy_export(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Exports sorting into ph
    carrier is updated with phy directory name.
    Returns updated carrier dictionary
    """

    logger = logging.getLogger( config['job_id'] + identifier )

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
    except:
        logger.error(f'`spikeinterfce[full]` must be installed to run sorting steps')
        raise RuntimeError(f'`spikeinterfce[full]` must be installed to run sorting steps')

    preproc = carrier[ dependencies[0] ]
    sorting = carrier[ dependencies[1] ]

    logger.info(f"EXPORTING PHY")
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
    
    phydir = config['job_evn']['base_directory']+'/'+ ( config[identifier]['folder'] if 'folder' in config[identifier] else 'phy')
    try:
        export_to_phy(
            sorting_analyzer = pyan,
            remove_if_exists = True,
            output_folder    = phydir
        )
    except BaseException as e:
        logger.error(f"Cannot export to phy: {e}")
        raise RuntimeError(f"Cannot create and analyzer: {e}")        
    carrier[identifier] = phydir
    logger.info(f" > exported to {phydir}")
    return carrier

###>><<<
    # if 'report' in analyzeconf:
        # if type(analyzeconf['report']) is str:
            # reportdir = config['job_evn']['base_directory']+'/'+analyzeconf['report']
            # if last['rerun']:
                # delosdir(reportdir)
            # from spikeinterface.exporters import export_report
            # try:
                # export_report(
                    # sorting_analyzer=analyzer, 
                    # output_folder=reportdir
                # )
            # except BaseException as e:
                # logger.error(f"Cannot export a report: {e}")
                # raise RuntimeError(f"Cannot export a report: {e}")
            # logger.info(f' > report is exported to {reportdir}')
        # else:
            # logger.error(f"report is not a string - cannot export the report")

###<<<
