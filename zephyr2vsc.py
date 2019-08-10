import sys
import os.path
import re
import io
import string
import json
import subprocess

def GetNinjaRules(everything):
    rulesFile = everything["ninjaRulesFile"]
    rules = []

    with open(rulesFile, "r") as f:
        lines = f.readlines()
    
    for line in lines:
        m = re.match(r"^rule\s([^\n]*)$", line)
        if(not m is None):
            rules.append(m.group(1))

    everything["ninjaRules"] = list(set(rules))
    print("Found [%d] ninja build rules in:\n[%s]\n" % (len(everything["ninjaRules"]), everything["ninjaRulesFile"]))
    return

def GetAllCFilesRelativePath(everything):
    srcDir = everything["srcDir"]
    allCFiles = []
    for _dir, _subdirs, _files in os.walk(srcDir):
        if(len(_files)==0):
            continue
        for _file in _files:
            if(_file[-2:] == ".c"):
                cFile = os.path.join(_dir, _file)
                allCFiles.append(os.path.relpath(cFile,srcDir)) # get the relative path to the srcDir
    
    everything["allCFiles"] = list(set(allCFiles))
#    for cFile in allCFiles:
#        print(cFile)
    print("Found [%d] C source files in source dir:\n[%s]\n" % (len(everything["allCFiles"]), everything["srcDir"]))
    return

def GetRelevantCFilesRelativePath(everything):
    buildFile = everything["ninjaBldFile"]
    srcDir = everything["srcDir"]
    bldDir = everything["bldDir"] 
    cFiles = []

    with open(buildFile, "r") as f:
        lines = f.readlines()
    
    for line in lines:
        m = re.match(r"^build\s.*\s([^\s|]+\.c)\s", line)
        if(not m is None):
            cFile = os.path.normpath(m.group(1).replace("$", ""))
            if(not os.path.isabs(cFile)):
                #This must be a build generated file
                cFiles.append(os.path.normpath(os.path.join(bldDir, cFile)))
            else:
                cFiles.append(os.path.relpath(cFile, srcDir))# get the relative path to the srcDir
    everything["cFiles"] = list(set(cFiles))
#    for cFile in cFiles:
#        print(cFile)
    print("Found [%d] relevant C source files.\n" % len(everything["cFiles"]))
    return

def GetExcludedCFilesRelativePath(everything):
    relevantCFilesSet = set(everything["cFiles"])
    allCFilesSet = set(everything["allCFiles"])
    excludeCFiles = allCFilesSet - relevantCFilesSet
    everything["excludeCFiles"] = list(set(excludeCFiles))
    print("Exclude [%d] irrelevant C source files.\n" % len(everything["excludeCFiles"]))
    return

def CreateDotVSCodeFolderInSrcDir(everything):
    vscodeDir = os.path.join(everything["srcDir"], ".vscode")
    everything["vscodeDir"] = vscodeDir
    if(os.path.exists(vscodeDir)):
        print(".vscode folder already exists source dir:\n[%s]\n" % everything["srcDir"])
        return
    os.mkdir(vscodeDir)
    print(".vscode folder generated for source dir:\n[%s]\n" % everything["srcDir"])
    return

def GenerateCompilationDB(everything):
    compDBFileFullpath = os.path.abspath(os.path.join(everything["bldDir"], "zephyr_compile_db.json")) # compDB will be saved in the bldDir
    allRulesString = " ".join(everything["ninjaRules"])
    cmdString = r"ninja -C <BLD_DIR> -t compdb <RULES>"
    cmdString = cmdString.replace(r"<BLD_DIR>", everything["bldDir"])
    #cmdString = cmdString.replace(r"<COMPDB_OUTPUT>", compDBFileFullpath)
    cmdString = cmdString.replace(r"<RULES>", allRulesString)

    print("Zephyr compilation DB will be saved as:\n[%s]\n" % compDBFileFullpath)
    with open(compDBFileFullpath, "w") as f:
        subprocess.run(cmdString, stdout=f, shell=True)

    f = open(compDBFileFullpath, "r")
    fixedLines = []
    for line in f.readlines():
        if("--imacros=" in line):
            fixedLines.append(line.replace("--imacros=", "-include")) # Windows workaround https://github.com/Microsoft/vscode-cpptools/issues/2417
        elif("-imacros" in line):
            fixedLines.append(line.replace("-imacros", "-include")) # Linux workaround https://github.com/Microsoft/vscode-cpptools/issues/2417
        else:
            fixedLines.append(line) 
    f.close()

    f = open(compDBFileFullpath, "w")
    f.writelines(fixedLines)
    f.close()   

    everything["compDBFileFullpath"] = compDBFileFullpath
    print("Zephyr compilation DB is saved as:\n[%s]\n" % compDBFileFullpath)
    return

def GenerateVSCConfigJSONs(everything):
    settings = everything["settings.json"]
    cprops = everything["c_cpp_properties.json"]
    settingsDecoded= None
    cpropsDecoded = None
    with open(settings, "r") as f:
        settingsDecoded = json.load(f)        
    with open(cprops, "r") as f:
        cpropsDecoded = json.load(f) 

    for excludedCFile in everything["excludeCFiles"]:
        settingsDecoded["files.exclude"][excludedCFile] = True
    
    settingsDecoded["files.exclude"]["**/.github"] = True
    settingsDecoded["files.exclude"]["**/.known-issues"] = True
    settingsDecoded["files.exclude"]["**/.*"] = True
    settingsDecoded["files.exclude"][".vscode"] = False

    cpropsDecoded["configurations"][0]["compileCommands"]= everything["compDBFileFullpath"]
    cpropsDecoded["configurations"][0]["compilerPath"]= everything["compilerPath"]

    CreateDotVSCodeFolderInSrcDir(everything)
    vscodeDir = everything["vscodeDir"]
    targetSettingsJsonFullpath = os.path.join(vscodeDir, "settings.json")
    targetCPropsJsonFullpath = os.path.join(vscodeDir, "c_cpp_properties.json")

    with open(targetSettingsJsonFullpath, "w") as f:
        json.dump(settingsDecoded, f)

    with open(targetCPropsJsonFullpath, "w") as f:
        json.dump(cpropsDecoded, f)

    print("VS Code configuration JSON files generated:\n[%s]\n[%s]\n" % (targetSettingsJsonFullpath, targetCPropsJsonFullpath))
    return

def GetNinjaRulesFile(everything):
    everything["ninjaRulesFile"]= os.path.join(everything["bldDir"], "rules.ninja")
    print("Ninja rules file found:\n[%s]\n" % everything["ninjaRulesFile"])
    return

def GetNinjaBuildFile(everything):
    everything["ninjaBldFile"]= os.path.join(everything["bldDir"], "build.ninja")
    print("Ninja build file found:\n[%s]\n" % everything["ninjaBldFile"])
    return

def LoadVSCJSONTemplates(everything):
    scriptDir = os.path.dirname(os.path.realpath(__file__))
    everything["settings.json"] = os.path.abspath(os.path.join(scriptDir, r"settings.json"))
    everything["c_cpp_properties.json"] = os.path.abspath(os.path.join(scriptDir, r"c_cpp_properties.json"))
    print("VS Code configuration JSON templates loaded.\n")
    return

def DeriveOtheConfigs(everything):
    GetNinjaRulesFile(everything)
    GetNinjaBuildFile(everything)
    LoadVSCJSONTemplates(everything)
    return


def DoWork(everything):
    print("Start generating VSCode workspace for\n[%s]\n" % everything["srcDir"])
    DeriveOtheConfigs(everything)    
    GetNinjaRules(everything)
    GetRelevantCFilesRelativePath(everything)
    GetAllCFilesRelativePath(everything)
    GetExcludedCFilesRelativePath(everything)

    GenerateCompilationDB(everything)
    GenerateVSCConfigJSONs(everything)
    print("Finished generating VSCode workspace for\n[%s]\n" % everything["srcDir"])
    return    

def Usage():
    print("Usage:\n")
    print("zephyr2vsc <srcDir> <bldDir> <compilerPath>")
    print("\t <srcDir>: the source code folder to open in VS Code.")
    print("\t <bldDir>: the build folder where build.ninja file is located.")
    print("\t <compilerPath>: the fullpath of the compiler")
    return


def CleanseArgs(everything):
    return
    


if __name__=="__main__":
    everything = dict()    
    if(len(sys.argv)!= 4):
        Usage()
    else:
        everything["srcDir"] = os.path.abspath(os.path.normpath(sys.argv[1])) # this is the folder to open in VS Code.
        everything["bldDir"] = os.path.abspath(os.path.normpath(sys.argv[2])) # this is the folder where build.ninja file is located.
        everything["compilerPath"] = os.path.abspath(os.path.normpath(sys.argv[3])) # this is the folder where build.ninja file is located.
        CleanseArgs(everything)
        DoWork(everything)
        
    sys.exit(0)
