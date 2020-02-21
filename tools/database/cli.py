#!/usr/bin/python3

"""
Front-end CLI for the leakage database
"""

import sys
import os
import gzip
import argparse
import datetime
import logging  as log
import configparser

import numpy as np

import ldb

ENTITY_CORES        = "cores"
ENTITY_DEVICES      = "devices"
ENTITY_BOARDS       = "boards"
ENTITY_TARGETS      = "targets"
ENTITY_EXPERIMENTS  = "experiments"
ENTITY_TTRACESETS   = "ttrace-sets"
ENTITY_TRACESETBLOBS= "traceset-blobs"

#
# Possible entity types we can list in the database.
list_command_options = [
    ENTITY_CORES        ,
    ENTITY_DEVICES      ,
    ENTITY_BOARDS       ,
    ENTITY_TARGETS      ,
    ENTITY_EXPERIMENTS  ,
    ENTITY_TTRACESETS   ,
    ENTITY_TRACESETBLOBS
]

def connectToBackend(path, backend):
    """
    Returns an appropriate instance of a database backend based on
    the supplied path and backend parameters.
    """
    if(backend == "sqlite"):
        return ldb.backend.SQLiteBackend("sqlite:///"+path)
    else:
        raise Exception("Unknown backend '%s'" % backend)


def commandInit(args):
    """
    Called when "init" is specified on the command line.
    """

    backend = None

    if(args.backend == "sqlite"):
        backend = ldb.backend.SQLiteBackend
    else:
        raise Exception("Invalid backend string: '%s'" % args.backend)

    file_exists = os.path.isfile(args.dbpath)

    if(file_exists and not args.soft and not args.force):
        log.error("The file '%s' already exists!" % args.dbpath)
        return 1
    elif(file_exists and args.soft and not args.force):
        log.info("The file '%s' already exists." % args.dbpath)
        return 0

    if(file_exists and args.force):
        log.warning("Removing pre-existing file '%s'" % args.dbpath)
        os.remove(args.dbpath)

    backend.createNew(args.dbpath)

    log.info("Created new %s backed database at %s" % (
        args.backend, args.dbpath))

    return 0


def commandInsertTargets(args):
    """
    Inserts a target device based on a description cfg of the type
    used by the browser tool.
    """

    if(args.from_cfg):

        backend = connectToBackend(args.dbpath, args.backend)
        backend.autocommit = False

        for cfg_path in args.from_cfg:
            cfg    = configparser.ConfigParser()
            cfg.read(cfg_path)

            core    = ldb.records.Core.fromCFGDict(cfg)
            board   = ldb.records.Board.fromCFGDict(cfg)
            device  = ldb.records.Device.fromCFGDict(cfg)

            if(backend.getCoreByName(core.name) == None):
                backend.insertCore(core)
            else:
                log.warn("Skipping core '%s', already exists." % core.name)

            if(backend.getBoardByName(board.name) == None):
                backend.insertBoard(board)
            else:
                log.warn("Skipping board '%s', already exists." % board.name)

            if(backend.getDeviceByName(device.name) == None):
                backend.insertDevice(device)
            else:
                log.warn("Skipping device '%s', already exists." % device.name)

            target  = ldb.records.Target.fromCFGDict(
                cfg, device.id, board.id, core.id
            )

            if(backend.getTargetByName(target.name) == None):
                backend.insertTarget(target)
            else:
                log.warn("Skipping target '%s', already exists." % target.name)

            backend.commit()

    else:
        log.warn("No target information to insert!")

    return 0


def commandListEntries(args):
    """
    A simple way to print out entries in the database.
    """
    assert(args.entity in list_command_options)
    backend = connectToBackend(args.dbpath, args.backend)

    items = []

    if  (args.entity == ENTITY_CORES):
        items = backend.getAllCores()

    elif(args.entity == ENTITY_DEVICES):
        items = backend.getAllDevices()

    elif(args.entity == ENTITY_BOARDS):
        items = backend.getAllBoards()
    
    elif(args.entity == ENTITY_TARGETS):
        items = backend.getAllTargets()
    
    elif(args.entity == ENTITY_EXPERIMENTS):
        items = backend.getAllExperiments()
    
    elif(args.entity == ENTITY_TTRACESETS):
        items = backend.getAllTTraceSets()
    
    elif(args.entity == ENTITY_TRACESETBLOBS):
        items = backend.getAllTraceSetBlobs()

    else:
        assert(False),"Should be unreachable!"
    
    for item in items:
        print(item)

    return 0


def commandInsertExperiment(args):
    """
    For inserting experiments into the database.
    If the supplied name/catagory combination already exists, then
    print the id of the existing entry. Otherwise print the id of
    the new entry.
    """
    backend = connectToBackend(args.dbpath, args.backend)

    existing = backend.getExperimentByCatagoryAndName(
        args.catagory,
        args.name
    )

    if(existing == None):

        newExperiment = ldb.records.Experiment(
            name        = args.name,
            catagory    = args.catagory,
            description = args.description
        )

        backend.insertExperiment(newExperiment)
        backend.commit()

        print(newExperiment.id)

    else:

        print(existing.id)

    return 0


def commandInsertTTest(args):
    """
    Insert a ttest record into the database
    """
    backend = connectToBackend(args.dbpath, args.backend)

    experiment_name     = args.experiment.partition("/")[2]
    experiment_catagory = args.experiment.partition("/")[0]

    experiment  = backend.getExperimentByCatagoryAndName(
        experiment_catagory, experiment_name
    )

    if(args.scope_config):
        cfg    = configparser.ConfigParser()
        cfg.read(args.scope_config)

        args.scope_samplerate = int(float(cfg["SCOPE"]["sample_freq"]))
        args.scope_resolution = int(cfg["SCOPE"]["resolution"])

    if(experiment == None):
        log.error("No such experiment '%s' / '%s'" % (
            experiment_catagory, experiment_name))
        return 1

    target      = backend.getTargetByName(args.target_name)

    if(target == None):
        log.error("No such target: '%s'" % args.target_name)
        return 2

    insert_new  = True
    id_toreturn = 0

    if(args.replace):
        candidates = backend.getTraceSetsForTargetAndExperiment(
            target.id, experiment.id
        )

        for candidate in candidates:
            
            eq_sr = candidate.scope_samplerate == args.scope_samplerate
            eq_res= candidate.scope_resolution == args.scope_resolution
            eq_df = candidate.device_freq      == args.device_freq     
            eq_name = candidate.name           == args.name
            eq_param= candidate.parameters     == args.parameters

            if(eq_sr and eq_res and eq_df and eq_name):

                candidate.timestamp = datetime.datetime.now()
                candidate.filepath_fixed = args.fixed_bits
                candidate.filepath_traces= args.traces
                backend.commit()
                id_toreturn = candidate.id
                insert_new  = False
                break

    if(insert_new):

        newTraceset = ldb.records.TraceSet (
            set_type        = "ttest",
            filepath_fixed  = args.fixed_bits,
            filepath_traces = args.traces,
            device_freq     = args.device_freq,
            scope_samplerate= args.scope_samplerate,
            scope_resolution= args.scope_resolution,
            experimentId    = experiment.id,
            targetId        = target.id,
            parameters      = args.parameters
        )

        backend.insertTraceSet(newTraceset)
        backend.commit()

        id_toreturn = newTraceset.id
    
    print(id_toreturn)

    return 0


def subCommandInsertStatTrace(tracelist, statType, traceset, compression, db):
    """
    Iterate over a list of traces in tracelist, which are all of type
    statType and created from the supplied TraceSet instance traceset.
    Insert each trace into the database.
    """

    for tfile in tracelist:

        fh = tfile

        if(not os.path.isfile(tfile)):
            log.error("Statistic trace does not exist: '%s'" % tfile)
            return 1

        if(isinstance(tfile,str) and tfile.endswith(".gz")):
            fh = gzip.GzipFile(tfile,"r")

        nparray = np.load(fh)

        to_insert   = ldb.records.StatisticTrace(
            filepath    = tfile,
            traceSetId  = traceset.id,
            compression = compression,
            traceType   = statType,
            trace       = nparray
        )

        db.insertStatisticTrace(to_insert)

    return 0

def commandInsertStatTraces(args):
    """
    Function for inserting statistic traces from disk into the database.
    """
    backend             = connectToBackend(args.dbpath, args.backend)
    backend.autocommit  = False

    parent_traceset     = None
    
    if(args.traceset_id != None):
        
        parent_traceset = backend.getTraceSetById(args.traceset_id)

    elif(args.traceset_filepath != None):
        
        parent_traceset = backend.getTraceSetByTracesFilepath(
            args.traceset_filepath
        )

    else:

        log.error("Must specify an assoicated traceset!")
        return 1

    if(parent_traceset == None):
        log.error("No traceset exists with id '%d'" % args.traceset_id)
        return 1

    subCommandInsertStatTrace (
        args.avg_trace,STAT_TYPE_AVG,parent_traceset,args.compression,backend
    )
    
    subCommandInsertStatTrace (
        args.std_trace,STAT_TYPE_STD,parent_traceset,args.compression,backend
    )
    
    subCommandInsertStatTrace (
        args.hw_trace,STAT_TYPE_HW,parent_traceset,args.compression,backend
    )

    subCommandInsertStatTrace (
        args.hd_trace,STAT_TYPE_HD,parent_traceset,args.compression,backend
    )
    
    backend.commit()

    return 0


def buildArgParser():
    """
    Return the ArgumentParser object used to parse command line arguments
    to the CLI app.
    """

    parser      = argparse.ArgumentParser()

    parser.add_argument("dbpath", type=str, 
        help="File-path of the database")

    parser.add_argument("--backend", choices=["sqlite"],
        default="sqlite", help="Database Backend To Use")

    parser.add_argument("--verbose","-v",action="store_true",
        help="Turn on verbose logging.")

    subparsers  = parser.add_subparsers(
        title="Sub-commands",
        dest="command"
    )
    subparsers.required = True
    
    #
    # Arguments for listing entries in the database
    
    parser_add_target = subparsers.add_parser("list",
        help="list entries in the database")
    
    parser_add_target.set_defaults(func=commandListEntries)

    parser_add_target.add_argument("entity", type=str, 
        choices=list_command_options,
        help="What sort of entity type in the database to list.")

    #
    # Arguments for inserting a new target, board, device and core from
    # A config used by the browser tool
    
    parser_add_target = subparsers.add_parser("insert-targets",
        help="Insert a new target into the database")
    
    parser_add_target.set_defaults(func=commandInsertTargets)

    parser_add_target.add_argument("--from-cfg", type=str, nargs="+",
        help="Insert Target, Device, Board and Core information from the supplied cfg file.")

    #
    # Arguments for adding a new experiment to the database

    parser_add_experiment = subparsers.add_parser("insert-experiment",
        help = "Add a new experiment to the database. If the experiment already exists, it is not updated.")
    
    parser_add_experiment.set_defaults(func=commandInsertExperiment)
    
    parser_add_experiment.add_argument("--catagory","-c", type=str,
        default = "miscellaneous",
        help="Catagory to which the experiment belongs.")
    
    parser_add_experiment.add_argument("--description","-d", type=str,
        default="",
        help="A short description of the experiment")

    parser_add_experiment.add_argument("name", type=str,
        help="The name of the experiment")
    
    #
    # Arguments for adding records of ttest trace sets to the database

    parser_add_ttest= subparsers.add_parser("insert-ttest-traces",
        help="Add a TTest trace set to the database")
    
    parser_add_ttest.set_defaults(func=commandInsertTTest)

    parser_add_ttest.add_argument("--scope-samplerate",type=int,default=0)
    parser_add_ttest.add_argument("--scope-resolution",type=int,default=0)
    parser_add_ttest.add_argument("--device-freq"     ,type=int,default=0)

    parser_add_ttest.add_argument("--scope-config", type=str,
        help="File path of scope configuration to use.")

    parser_add_ttest.add_argument("--replace", action="store_true",
        help="If present, replace any existing trace set records with the same name, experiment, target, scope and device configuration with this one. Otherwise, just add a new entry.")

    parser_add_ttest.add_argument("--name", type=str,
        default = "ttest",
        help ="A friendly-ish name for the TTest trace set.")
    
    parser_add_ttest.add_argument("--parameters", type=str,
        default = "",
        help ="A string of <name>=<value> separated items repreenting parameters to the trace capture.")

    parser_add_ttest.add_argument("target_name", type = str,
        help="Name of the target which this trace set is associated with")
    
    parser_add_ttest.add_argument("experiment", type = str,
        help="Name of the experiment in the form '<catagory>/<name>'")

    parser_add_ttest.add_argument("fixed_bits",
        type=str,
        help="Filepath to the npy file indicating which traces are fixed or random")

    parser_add_ttest.add_argument("traces",
        type=str,
        help="Filepath to the npy file containing the raw traces.")

    #
    # Arguments for inserting a new statistic trace

    parser_add_stat = subparsers.add_parser("insert-statistic-traces",
        help="Insert a statistic trace associated with a trace set")

    parser_add_stat.set_defaults(func=commandInsertStatTraces)

    parser_add_stat_traceset = parser_add_stat.add_mutually_exclusive_group(
        required = True
    )

    parser_add_stat_traceset.add_argument("--traceset-id",type = int,
        default = None,
        help="ID of the trace set from which this statistic trace is derived")

    parser_add_stat_traceset.add_argument("--traceset-filepath",type=str,
        default = None,
        help="Filepath of the traceset from which this statistic trace is derived.")

    parser_add_stat.add_argument("--compression", type=str,
        choices = ldb.records.TraceCompression.__members__.items(),
        default = "NONE",
        help="Whether and how to compress the trace in the database")
    
    parser_add_stat.add_argument("--avg-trace", type=str,nargs="*")
    parser_add_stat.add_argument("--std-trace", type=str,nargs="*")
    parser_add_stat.add_argument("--hw-trace", type=str,nargs="*")
    parser_add_stat.add_argument("--hd-trace", type=str,nargs="*")

    #
    # Arguments for initialising a new database

    parser_init = subparsers.add_parser("init",
        help="Create a new database file")

    parser_init.set_defaults(func=commandInit)

    parser_init.add_argument("--soft", action="store_true",
        help="Don't raise an error if the destination file already exists.")
    
    parser_init.add_argument("--force", action="store_true",
        help="Remove the existing database file if it already exists.")

    return parser


def main():
    """
    CLI main function
    """
    parser = buildArgParser()
    args   = parser.parse_args()

    if(args.verbose):
        log.basicConfig(level=log.INFO)
    else:
        log.basicConfig(level=log.WARN)

    result = args.func(args)

    return result


if(__name__=="__main__"):
    rcode = main()
    sys.exit(rcode)
