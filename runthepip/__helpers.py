"""
Helpers for main functions of CLI interface and SSLH-worker
"""


def __get_dep_step(config:dict, idf:str):
    if not 'job_steps' in config:
        raise RuntimeError(f'cannot find job_steps in configuration ')
    jobsteps = config['job_steps']
    for s in jobsteps:
        if s['identifier'] == idf :
            return s['function']
    raise RuntimeError(f'cannot find `{idf}` in job_steps')
