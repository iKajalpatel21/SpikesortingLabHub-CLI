import  os,\
       sys,\
    logging,\
     shutil
import json
import psutil
from numpy import *
import copy as pycopy
from __helpers import * 

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


def recording(config:dict,identifier:str,dependencies:(list,tuple),carrier:dict):
    """
    Reads a recording, sets probe configuration, used channels, and bad channels.
    
    """
    logger = logging.getLogger(os.path.basename(config['job_id']+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeErrorf('Cannot find `{identifier}` in the configuration')

    recconf = config[identifier]
    if not type(recconf) is dict:
        logger.error(f'incorrect type of the `{identifier}` entrance: got {type(recconf)} but should be a dictionary')
        raise RuntimeErrorf(f'incorrect type of the `{identifier}` entrance: got {type(recconf)} but should be a dictionary')
    
    
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
        raise RuntimeErrorf(f'`spikeinterfce[full]` must be installed to run sorting steps')
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

    logger = logging.getLogger(os.path.basename(config['job_id']+identifier )

    if not identifier in config:
        logger.error(f'Cannot find `{identifier}` in the configuration')
        raise RuntimeErrorf('Cannot find `{identifier}` in the configuration')

    preprocconf = config[identifier]
    if not type(preprocconf) is dict:
        logger.error(f'incorrect type of the `{identifier}` entrance: got {type(preprocconf)} but should be a dictionary')
        raise RuntimeErrorf(f'incorrect type of the `{identifier}` entrance: got {type(preprocconf)} but should be a dictionary')
    
    
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
        raise RuntimeErrorf(f'`spikeinterfce[full]` must be installed to run sorting steps')
    
    
    # if last['rerun']:
        # delosdir('{running directory}/{folder}'.format(folder=(preprocconf['folder'] if 'folder' in preprocconf else "preprocessed"),**last))

    if not   'methods' in preprocconf:
        logger.error(f'There is not a `methods` section in `{identifier}` section')
        raise RuntimeError(f'There is not a `methods` section in `{identifier}` section')
    if not type(preprocconf['methods']) is list:
        logger.error(f'The `methods` section in `{identifier}` section is not a list')
        raise RuntimeError(f'The `methods` section in `{identifier}` section is not a list')
    if len(dependencies) != 1:
        logger.error(f'dependencies must have only one identifier but got {len(dependencies)}')
        raise RuntimeError(f'dependencies must have only one identifier but got {len(dependencies)}')
    
    preproc = [ carrier[ dependencies[0] ] ]s
    for ppm in preprocconf['methods']:
        logger.info(f"PREPROC: {ppm}")
        config = preprocconf[ppm] if ppm in preprocconf else None
        try:
            preproc.append( resolvepreproc(si, ppm, preproc[-1],config,logger) )
        except BaseException as e:
            logger.error(f'Cannot perform {ppm} in `{identifier}` section: {e}')
            raise RuntimeError(f'Cannot perform {ppm} in `{identifier}` section: {e}')

    preproc[-1].annotate(is_filtered=True)
### WARNING > base sorting directory (i.e. last['running directory'])  should be replaced with something
    preproc_saved = preproc[-1].save(
        folder = last['running directory']+'/'+(preprocconf['folder'] if 'folder' in preprocconf else identifier), 
        chunk_duration = si.get_global_job_kwargs()['chunk_duration']
        )
### <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    carrier[identifier] = preproc_saved
    return carrier


    
    
        
