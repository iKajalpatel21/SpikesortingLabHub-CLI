import  os,\
       sys,\
    logging,\
     shutil,\
     time,\
     re
import json
import psutil
from numpy import *
import copy as pycopy

try:
    import importlib  
    sslh = importlib.import_module("sslh-cli")
except:
    import os.path
    HERE = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
    sys.path.insert(0, HERE)
    sslh = importlib.import_module("sslh-cli")


# Replace $JOB_ID$, $LOCAL$, and $NAS$ in the entire job configuration
def resolve_paths(config:(dict,list,tuple), local:str, nas:str, jobID:str)->(dict,list,tuple):
    if type(config) is dict:
        for n in config:
            if type(config[n]) in (dict,list,tuple):
                config[n] = resolve_paths(config[n],local,nas,jobID)
            elif type(config[n]) is str:
                config[n] = config[n].replace('$LOCAL$',local).replace('$NAS$',nas).replace('$JOB_ID$',jobID)
        return config
    else:
        return [
            resolve_paths(x,local,nas,jobID) if type(x) in (dict,list,tuple) else \
            (
                x.replace('$LOCAL$',local).replace('$NAS$',nas).replace('$JOB_ID$',jobID) \
                if type(x) is str else \
                x
            )
            for x in config
        ]    

# Dynamically load a function from sslh
def get_a_function(name:str):
    try:        
        fn = getattr(sslh, name)
    except AttributeError:
        raise ValueError(f"[Worker] Step `{step_name}` not found in `{STEP_MODULE}`")
    return fn

def set_logging(job_conf:dict)->(int,str):
    loglevel = job_conf['job_evn'].get('log_level', 'INFO')
    logfile  = job_conf['job_evn']['REDIRECT']['log']\
        if 'REDIRECT' in job_conf['job_evn'] and 'log' in job_conf['job_evn']['REDIRECT'] else \
        job_conf['job_evn']['base directory']+'/'+job_conf['job_id']+'.log'
    try:
        os.makedirs(
            os.path.dirname(logfile), 
            exist_ok=True
        )
    except BaseException as e:
        return f'Cannot create directory logging directory: {e}'
    try:
        logging.basicConfig(
            filename = logfile,
            level    = eval(f'logging.{loglevel}'),
            format   = '%(asctime)s:%(name)-33s:%(lineno)-6d%(levelname)-8s:%(message)s'
        )
    except BaseException as e:
        return f'Cannot setup logging: {e}'
    return 0

def set_std(job_conf:dict)->(int,str):
    set_std.stdout = None
    set_std.stderr = None
    outfile = job_conf['job_evn']['REDIRECT']['out'] if 'REDIRECT' in job_conf['job_evn'] and 'out' in job_conf['job_evn']['REDIRECT'] else None
    errfile = job_conf['job_evn']['REDIRECT']['err'] if 'REDIRECT' in job_conf['job_evn'] and 'err' in job_conf['job_evn']['REDIRECT'] else None
    if not outfile is None:
        try:
            os.makedirs(
                os.path.dirname(outfile), 
                exist_ok=True
            )
        except BaseException as e:
            return f'Cannot create directory for stdout file: {e}'
        set_std.stdout  = sys.stdout
        sys.stdout      = open(outfile,'a')
    if not errfile is None:
        try:
            os.makedirs(
                os.path.dirname(errfile), 
                exist_ok=True
            )
        except BaseException as e:
            return f'Cannot create directory for stderr file: {e}'
        set_std.stderr  = sys.stderr
        sys.stderr      = open(errfile,'a')
    return 0

def restory_std(message:(str,None)=None)->(str,int):
    if message is None:
        if not set_std.stderr is None:
            sys.stderr = set_std.stderr
        if not set_std.stdout is None:
            sys.stdout = set_std.stdout
        return 0
    else:
        sys.stderr.write('\n' + message + '\n' )
        if not set_std.stderr is None:
            sys.stderr = set_std.stderr
            sys.stderr.write('\n' + message + '\n' )
        if not set_std.stdout is None:
            sys.stdout = set_std.stdout
        return message

# Utility to create a working directory for a job and save configuration in it
def create_base_directory_and_save_pipeline_json(job_config:dict)->(int,str):
    basedir = job_config['job_evn']['base directory']
    job_id  = job_config['job_id']
    try:
        os.makedirs(basedir, exist_ok=True)
    except BaseException as e:
        logging.error(f'Cannot create the base directory: {e}')
        return f'Cannot create the base directory: {e}'
    jobfilename = os.path.join(basedir, f"sslh-{job_id}.json")
    try:
        with open(jobfilename, "w") as fd:
            json.dump(job_config, fd, indent=4)
    except BaseException as e:
        logging.error(f'Cannot save job configuration into the file `{jobfilename}`: {e}')
        return f'Cannot save job configuration into the file `{jobfilename}`: {e}'
    return 0


def run_the_job(config:dict, job_conf, api:(dict,None)=None, proconly:list=[]):
    if not api is None:
        if not 'status_updater' in api:
            return f'API is set but there is no status_updater key with updater function'
        update_status = api['status_updater']
    x = sslh.base_check(job_conf)
    if x != 0 :
        return f'Base Configuration Checkout fails :{x}'
    # Resolve all paths at ones
    job_conf = sslh.resolve_paths(job_conf, config["LOCAL"], config["NAS"], job_conf["job_id"])
    
    # setting log
    x = sslh.set_logging(job_conf)
    if x != 0:
        return f'Cannot set up log file: {x}'
    # setting stdout and stderr
    x = sslh.set_std(job_conf)
    if x != 0:
        return f'Cannot set up stdout/stderr files: {x}'
    
    x = sslh.job_sanity_check(job_conf)
    logging.debug(f"--->JOB Sanity: {x}")
    if x != 0:
        logging.error(f'Config did not pass sanity check: {x}')
        return restory_std(f'Config did not pass sanity check:\n   {x}')
    # creating the base directory
    x = sslh.create_base_directory_and_save_pipeline_json(job_conf)
    if x != 0:
        logging.error(f'Cannot create or save job JSON: {x}')
        return restory_std(f'Cannot create or save job JSON:\n   {x}')
    
    dryrun = config.get('dryrun',False)
    if len(proconly) == 0:
        proconly = [ step['identifier'] for step in job_conf['job_steps'] ]
    # Main job loop
    job_id = job_conf['job_id']
    logging.info(f"Job {job_id} runs")
    if not api is None: update_status(job_id, None, "running", **api)
    carrier = {}
    for step in job_conf['job_steps']:
        function     = step[ 'function' ]
        identifier   = step['identifier']
        depends      = step[ 'depends'  ]
        if not identifier in proconly:
            # Actually it is a bug.
            # The carrier needs an object for farther processing
            # So here should be an object loading call
            continue
        
        if not api is None: update_status(job_id,identifier, "running", **api)
        logging.info(f" > Step: {function}:{identifier} runs")
        try:
            fn = sslh.get_a_function(function)
        except BaseException as e:
            logging.error(f'Cannot import `{function}` from `sslh` module')
            if not api is None: update_status(job_id,identifier, "failed", **api)
            return restory_std(f'Cannot import `{function}` from `sslh` module')

        if dryrun:
            time.sleep(3)
        else:
            try:
                carrier = fn(
                    job_conf,
                    identifier,
                    depends,
                    carrier )
            except BaseException as e:
                logging.error(f'Step function {function} #{identifier} returned an error: {e}')
                if not api is None: update_status(job_id,identifier, "failed", **api)
                return restory_std(f'Step function {function} #{identifier} returned an error: {e}')
        logging.info(f" > Step: {function}:{identifier} finished")
        if not api is None: update_status(job_id,identifier, "completed", **api)
    logging.info(f"Job {job_id} Finished")
    if not api is None: update_status(job_id, None, "completed", **api)
    return restory_std()

def update_env(last:dict,ncpu,memory,chunkdur,progress)->dict:
    if ncpu:
        if "job_evn" in last and "job_kwargs" in last["job_evn"] and "n_jobs"  in last["job_evn"]["job_kwargs"]:
            last["job_evn"]["job_kwargs"]["n_jobs"] = ncpu
        elif "job_evn" in last and "job_kwargs" in last["job_evn"]:
            last["job_evn"]["job_kwargs"] = { "n_jobs" : ncpu }
        else:
            last["job_evn"] = { "job_kwargs" : { "n_jobs" : ncpu } }            
    if memory:
        memory = f"{int(psutil.virtual_memory()[1]*memory/ncpus)//1024//1024//1024:d}G",
        if "job_evn" in last and "job_kwargs" in last["job_evn"] and "total_memory"  in last["job_evn"]["job_kwargs"]:
            last["job_evn"]["job_kwargs"]["total_memory"] = memory
        elif "job_evn" in last and "job_kwargs" in last["job_evn"]:
            last["job_evn"]["job_kwargs"] = { "total_memory" : memory }
        else:
            last["job_evn"] = { "job_kwargs" : { "total_memory" : memory } }
    if chunkdur:
        if "job_evn" in last and "job_kwargs" in last["job_evn"] and "chunk_duration"  in last["job_evn"]["job_kwargs"]:
            last["job_evn"]["job_kwargs"]["chunk_duration"] = chunkdur
        elif "job_evn" in last and "job_kwargs" in last["job_evn"]:
            last["job_evn"]["job_kwargs"] = { "chunk_duration" : chunkdur }
        else:
            last["job_evn"] = { "job_kwargs" : { "chunk_duration" : chunkdur } }
    if progress:
        if "job_evn" in last and "job_kwargs" in last["job_evn"] and "progress_bar"  in last["job_evn"]["job_kwargs"]:
            last["job_evn"]["job_kwargs"]["progress_bar"] = progress
        elif "job_evn" in last and "job_kwargs" in last["job_evn"]:
            last["job_evn"]["job_kwargs"] = { "progress_bar" : progress }
        else:
            last["job_evn"] = { "job_kwargs" : { "progress_bar" : progress } }
    return last
        
def timelimiter(config:dict, last:dict, proconly:list, timelimit:float):
    logger = logging.getLogger(os.path.basename(last['job_id'])+"-timelimiter" )
    logger.info("Time limit is active and set to {} hours =  {} seconds".format(last['time_limit'],int( round(last['time_limit']*3600) )))
    import signal
    def signal_handler(signum, frame):
        raise Exception(f"Time limit {timelimit} is out")
    signal.signal(signal.SIGALRM, signal_handler)
    timelimit =  int( round(last['time_limit']*3600) )
    signal.alarm(timelimit)
    logger.info(f'set time limit to {timelimit} seconds')
    try:
        ret = run_the_job(config, last, proconly=proconly)
    except BaseException as e:
        logger.error(f'Run failed woth error message {e}')
        return 1
    signal.alarm( 0 )
    return ret
            
def main()->int:
    from optparse import OptionParser
    oprs = OptionParser("USAGE: %prog [flags] running_task.json")
    oprs.add_option('-L' ,"--path-to-local-directory" , dest="local",default='.',     type="str",\
            help="path to local storage")
    oprs.add_option('-A' ,"--path-to-NAS"             , dest="NAS", default='.',     type="str",\
            help="path to NAS storage")

    oprs.add_option('-p' ,"--process-only"            , dest="proconly" , default=[],  action="append", type="str",\
            help="allows to run only specific job step with given identifier. It can be evoked multiple times to run subset of steps (default ALL in the file)")

    oprs.add_option("-N", "--ncpu"               ,  dest="ncpu"    , default=False,   type='int',\
            help="Use N CPU.  If not uses job environment setting or spikeinterface defaults")
    oprs.add_option("-M", "--memory"             ,  dest="memory"  , default=False,   type='float',\
            help="Use M-fraction of total memory (format 0.9).  If not uses job environment setting or spikeinterface defaults")
    oprs.add_option("-C", "--chunk-duration"     ,  dest="chunkdur", default=False,   type='str',\
            help="Set global chunk duration (format 90s). If not uses job environment setting or spikeinterface defaults")
    oprs.add_option('-B' ,"--progress-bar"       , dest="progress" , default=False,  action="store_true",\
            help="Run with progressive bar")
    oprs.add_option("-T", "--Time-limit"         ,  dest="timelim" , default=False,   type='float',\
            help="Time limit in hours (default: set by pipeline)")

    # oprs.add_option('-A' ,"--Absolute-path"      , dest="relpaths" , default=True,   action="store_false",\
            # help="Use absolute paths instead of relative one")
    # oprs.add_option("-P", "--pipeline"           ,  dest="pipeline", default=False,   type='str',\
            # help="Replaces all root entries from the pipeline JSON file") 
    # oprs.add_option("-R", "--Replace-from"       ,  dest="repl"    , type='str',     action="append",\
            # help="Recursive Replacement from JSON in the main run")
    # oprs.add_option('-S' ,"--save-json-file"     ,  dest="saveas"  , default=False,   type='str',\
            # help="Save combined json into file")
    # oprs.add_option('-W' ,"--Working-directory"  ,  dest="wordir"  , default=False,   type='str',\
            # help="Set working directory (default use from json file)")
    # oprs.add_option('-U' ,"--Update-state"       , dest="updatejs" , default=False,  action="store_true",\
            # help="Update state of sorting (default False)")
    oprs.add_option("-X", "--dry-run"            , dest="dryrun"   , default=False,  action="store_true",\
        help="Dry run for upload section")


    opts, args = oprs.parse_args()
    env_cof    = {
        "LOCAL" : opts.local,
        "NAS"   : opts.NAS,
        "dryrun": opts.dryrun
    }
        

    for arg in args:
        if os.path.isfile(arg):
            try:
                with open(arg) as fd:
                    last = json.load(fd)
            except BaseException as e:
                sys.stderr.write(f'**cannot read {arg}: {e}**\n')
                return 1
        else:
            sys.stderr.write(f'**Skipping {arg} as it is not a file**\n')
            continue
        x = sslh.base_check(last)
        if x != 0 :
            sys.stderr.write(f'Skipping {arg} - basic check returns an error :{x}')
            continue
        last = update_env(last, opts.ncpu, opts.memory, opts.chunkdur, opts.progress) 
        if opts.timelim:
            ret = timelimiter(env_cof,last,opts.proconly,opts.timelim)
        else:
            ret = run_the_job(env_cof,last,proconly = opts.proconly)
        if ret != 0:
            sys.stderr.write(f'sslh-cli.main: Sorting {arg} failed :{ret}')
            return ret
                
                    

if __name__ == "__main__":
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(main())
    

