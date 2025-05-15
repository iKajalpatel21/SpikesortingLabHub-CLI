"""
Helpers for main functions of CLI interface and SSLH-worker
"""
import shutil, os


def get_dep_step(config:dict, idf:str):
    if not 'job_steps' in config:
        raise RuntimeError(f'cannot find job_steps in configuration ')
    jobsteps = config['job_steps']
    for s in jobsteps:
        if s['identifier'] == idf :
            return s['function']
    raise RuntimeError(f'cannot find `{idf}` in job_steps')

def getospath(path:str):
    return os.sep.join([ n for m in path.split('/') for n in m.split('\\') ])
def delosdir(path:str, ignore_errors:bool=True):
    return shutil.rmtree(getospath(path), ignore_errors=ignore_errors)

def set_si_kwargs(si, config:dict)->dict:
    gkwargs = si.get_global_job_kwargs()
    lkwargs = config['job_evn']['job_kwargs']
    for x in gkwargs:
        if not x in lkwargs:
            lkwargs[x] = gkwargs[x]
    return lkwargs

def check_schema_an_enry(entry,sch)->(int,str):
    """
    Recursively checks if an `entry` is consistent with the schema `sch`
    RETURNS: 0 or a string with error message.
    """
    if   type(sch) is tuple:
        for s in sch:
            x = check_schema_an_enry(entry,s)
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
                x = check_schema_an_enry(ent,sch[0])
                if x != 0:
                    return f'list entry #{entid} returns error: {x}'
            return 0
        elif len(sch) != len(entry):
            return f'size of {sch} and {entry} are not the same'
        else:
            for entid,(s,e) in enumerate(zip(sch,entry)):
                x = check_schema_an_enry(e,s)
                if x != 0:
                    return f'list entry #{entid} returns error: {x}'
            return 0
    elif type(sch) is dict:
        if not type(entry) is dict: return f'entry `{entry}` is not a dictionary'
        for n in sch:            
            if not n[0] in ('*','>'):
                if n != '++':
                    return f'schema error: find entrance `{n}` which does not start from `*` or `>` and is not `++`'
        reqnames = [ x[1:] for x in sch if x[0] == '*' ]
        optnames = [ x[1:] for x in sch if x[0] == '>' ]
        allnames = [ x[1:] for x in sch                ]
        for n in reqnames:
            if not n in entry:
                return f'key `{n}` is missing in entry `{entry}`'
            x = check_schema_an_enry(entry[n],sch['*'+n])
            if x != 0:
                return f'dictionary entry {n} returns error: {x}'
        for n in optnames:
            if not n in entry: continue
            x = check_schema_an_enry(entry[n],sch['>'+n])
            if x != 0:
                return f'dictionary entry {n} returns error: {x}'
        for n in entry :            
            if   not n in allnames:
                if '+' in allnames:
                    x = check_schema_an_enry(entry[n],sch['++'])
                    if x != 0:
                        return f'while card `++` and dictionary entry {n} returns error: {x}'
                else:
                    return f'unknown entry `{n}` for a dictionary'
        return 0
    else:
        return f'we should be here! {entry}, {sch}'

def recursive_schema(d:dict, mitigate_none=False)->dict:
    """
    Builds schema based on default dictionary `d`.
    If default parameter is None and mitigate_none is set
    adds all dict and possible entrance.
    
    RETURNS: schema dictionary
    
    TODO: maybe `mitigate_none` should add all possible
    entrances such as (None, dict, list, float, int, bool, complex)....
    Just in case
    """
    res = {}
    for x in d:
        if   type(d[x]) is dict:
            res['>'+x] = recursive_schema(d[x])
        elif type(d[x]) is list:
            res['>'+x] = [ type(y) for y in d[x] ]
        elif d[x] is None and mitigate_none:
            res['>'+x] = (None, dict)
        else:
            res['>'+x] = type(d[x])
    return res
