# Spikesorting LabHub - Command Line interface

sslh-cli is a command interface that allows running spike sorting jobs locally.
It requires at least one job file as a command-line argument to perform any task.

## Installation
```bash
pip install git+https://github.com/UserFriendlySpikesorting/SpikesortingLabHub-CLI.git
``

## Usage
```bash
$ sslh-cli --help
Usage: sslh-cli [options] running_task.json [another_taks.json [ ... ] ]

Options:
  -h, --help            show this help message and exit
  -L LOCAL, --path-to-local-directory=LOCAL
                        path to local storage
  -A NAS, --path-to-NAS=NAS
                        path to NAS storage
  -N NCPU, --ncpu=NCPU  Use N CPU.  If not set, the parameters in use the job environment setting or
                        spikeinterface defines number of used CPU
  -M MEMORY, --memory=MEMORY
                        Use M-fraction of total memory (format 0.9).  If not set
                        it uses job environment setting or spikeinterface
                        defaults
  -C CHUNKDUR, --chunk-duration=CHUNKDUR
                        Set global chunk duration (format 90s). If not set it uses
                        job environment setting or spikeinterface defaults
  -B, --progress-bar    Run with progressive bar
  -T TIMELIM, --Time-limit=TIMELIM
                        Time limit in hours (default: set by pipeline)
  -X, --dry-run         Dry run
```

Example of running two sorting jobs with the same local directory and the same NAS directory to upload sorting results.
```bash
sslh-cli -L /local/sslh-cli-test -A /local/sslh-cli-nas -B -N 16 test.json another-test.json
```

The same example with a limit of 1/2 hour for each sorting job.
```bash
sslh-cli -L /local/sslh-cli-test -A /local/sslh-cli-nas -B -N 16 -T 0.5 test.json another-test.json
```

## Job file format

The job file is a JSON structure with a dictionary in the root.

The required fields are:

|Entry|Type  |Meaning           |
|:----|:----:|:-----------------|
|`version`|string|Protocol version|
|`si`	  |string| Spike interface version |
|`job_id` |string| Job ID |
|`job_evn`|dict|Environment for the entire job |
|`job_steps`| list| A list with all steps needed to accomplish the job|


### Job environment

The job environment must have at least two entrances:


|Entry|Type  |Meaning           |
|:----|:----:|:-----------------|
|`base_directory` | string | path for base directory |
|`job_kwarg` |dict | job parameters for SpikeInterface (see SpikeInterface documentation) |


An optional entrance `REDIRECT` allows redirecting `log`, standard output (`out`), and standard error (`err`) streams to files in the $LOCAL$ or $NAS$ directory.
The `REDIRECT` value must be a dictionary in which the corresponding stream name is a key, and the file path is a value.

### Job steps

Each job step is a dictionary with three required fields:


|Entry|Type  |Meaning           |
|:----|:----:|:-----------------|
|`function`|string| the function name which will be executed |
|`identifier`|string|The key of the entry in the job dictionary with parameters for this job and id of step result in ‘circulating’ dictionary|
|`depends`|list| The list of identifiers which needed for this step |


Example
```json
{
    "version" : "0.4.1",
    "si"      : "0.101.0",
    "job_id"  : "c7df2f67-b3f6-460b",
    "job_evn" : {
        "base directory" : "$LOCAL$/$JOB_ID$",
        "job_kwargs"     : {
            "n_jobs"         :  40  ,
            "total_memory"   : "128G",
            "chunk_duration" : "60s",
            "progress_bar"   : true
        },
        "log_level" : "DEBUG",
        "REDIRECT" : {
            "log" : "$NAS$/SORTING_LOGS/$JOB_ID$/run.log",
            "out" : "$NAS$/SORTING_LOGS/$JOB_ID$/run.out",
            "err" : "$NAS$/SORTING_LOGS/$JOB_ID$/run.err"
        }

    },
    "job_steps" : [
        { "function"   : "recording"    , "identifier" : "7ea0910ccea1", "depends"    : [] },
        { "function"   : "preprocessing", "identifier" : "754fed717d11", "depends"    : ["7ea0910ccea1"] },
        { "function"   : "sorting"      , "identifier" : "876194051d93", "depends"    : ["754fed717d11"] },
        { "function"   : "analyzer"     , "identifier" : "a12959d82f54", "depends"    : ["754fed717d11", "876194051d93"] },
        { "function"   : "phy_export"   , "identifier" : "500373039381", "depends"    : ["754fed717d11", "876194051d93"] },
        { "function"   : "upload"       , "identifier" : "dadb9f1689be", "depends"    : [] }
    ],
    "7ea0910ccea1" : {
        "binfile": "/data/20240320_GAD2_P8B_PSAM4_Thamus_rec_Thalamus-truncated.dat",
        "sampling rate": 30000.0,
        "number of channels": 256,
        "gain_to_uV": 0.1949999928474426,
        "offset_to_uV": 0.0,
        "probe": "$LOCAL$/probes/A8x32-Edge-5mm-25-200-177-after-mapping.json",
        "bad_channels": [ 130, 131, 140, 211, 255 ]
    },
    "754fed717d11" : {
        "methods": [
            "highpass or band filtering",
            "referensing"
        ],
        "highpass or band filtering": {
            "btype": "bandpass",
            "band": [
                131.4997033207064,
                7058.648254359456
            ]
        },
        "referensing": {
            "reference": "local",
            "operator": "median",
            "groups": null,
            "ref_channel_ids": [],
            "local_radius": [
                28,
                142
            ]
        },
        "zscore": {
            "mode": "median+mad"
        }
    },
    "876194051d93" : {
        "name": "hdsort",
        "parameters": {
            "loop_mode": "local_parfor",
            "chunk_memory": "500M",
            "chunk_size": 3870000,
            "filter": false,
            "freq_min": 50,
            "freq_max": 10000,
            "parfor": true,
            "detect_sign": -1,
            "detect_threshold": 4.1769714795783655,
            "max_el_per_group": 8,
            "min_el_per_group": 1,
            "max_distance_within_group": 343,
            "add_if_nearer_than": 292,
            "n_pc_dims": 3
        },
        "folder" : "sorting-saved",
        "image"  : "$LOCAL$/images/hdsort-compiled-base:latest.sif"

    },
    "500373039381" : {
    },
    "a12959d82f54" : {
        "metrics": {
            "quality_metrics": {
                "qm_params": {
                    "isi_violation": {
                        "isi_threshold_ms": 2.0
                    }
                }
            },
            "waveforms": {
                "ms_before": 1.5,
                "ms_after": 2.5
            },
            "spike_amplitudes": {
                "peak_sign": "neg"
            },
            "spike_locations": {
                "ms_before": 5.0,
                "ms_after": 5.0,
                "method": "center_of_mass"
            },
            "unit_locations": {
                "method": "center_of_mass"
            },
            "correlograms": {
                "window_ms": 500.0,
                "bin_ms": 1.0,
                "method": "auto"
            },
            "isi_histograms": {
                "window_ms": 500.0,
                "bin_ms": 1.0,
                "method": "auto"
            },
            "principal_components": {
                "n_components": 5,
                "mode": "by_channel_local",
                "whiten": false
            },
            "template_similarity": {
                "method": "cosine_similarity"
            }
        }
    },
    "dadb9f1689be" : {
        "destination" : "$NAS$/$JOB_ID$"
    }
}
```
