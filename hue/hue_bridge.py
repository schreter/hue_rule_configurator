'''
Created on 20 Nov 2018

@author: Ivan Schreter
'''
import requests
import json
import re
from copy import deepcopy
import pprint

VAR_PATTERN = re.compile("\\${([^}:]+):([^}]+)}")
SCENE_PATTERN = re.compile("^([^:]+):(.*)$")
OFF_BINDING = { "type": "scene", "configs": [ {"scene": "off"} ] }

BUTTON_MAP = {
    # mapping for dimmer
    "on": "1000",
    "on-release": "1002",
    "on-hold": "1001",
    "on-hold-release": "1003",
    "brighter": "2000",
    "brighter-release": "2002",
    "brighter-hold": "2001",
    "brighter-hold-release": "2003",
    "darker": "3000",
    "darker-release": "3002",
    "darker-hold": "3001",
    "darker-hold-release": "3003",
    "off": "4000",
    "off-release": "4002",
    "off-hold": "4001",
    "off-hold-release": "4003",
    # mapping for tap switches (normal)
    "1": "34",
    "2": "16",
    "3": "17",
    "4": "18",
    # mapping for tap switches on the wall
    "top-left": "16",
    "tl": "16",
    "top-right": "34",
    "tr": "34",
    "bottom-left": "17",
    "bl": "17",
    "bottom-right": "18",
    "br": "18",
    "top-both": "101",
    "tlr": "101",
    "bottom-both": "99",
    "blr": "99"
    }

class HueBridge():
    """
    Class for configuring various sensor rules in Philips Hue bridge using a simple JSON description

    See README.md for description of the configuration.
    """

#     # Original rules to append to bindings for a dimmer for dimming up/down. Requires group set in descriptor.
#     DIMMER_RULES = {
#         "brighter": { "type": "dim", "value": 30 },
#         "brighter-hold": { "type": "dim", "value": 56 },
#         "brighter-hold-release": { "type": "dim", "value": 0, "tt": 0 },
#         "darker": { "type": "dim", "value": -30 },
#         "darker-hold": { "type": "dim", "value": -56 },
#         "darker-hold-release": { "type": "dim", "value": 0, "tt": 0 }
#     }

    # Simpler rules to append to bindings for a dimmer for dimming up/down. Requires group set in descriptor.
    DIMMER_RULES = {
        "brighter": { "type": "dim", "value": 254, "tt": 35 },
        "brighter-any-release": { "type": "dim", "value": 0, "tt": 0 },
        "darker": { "type": "dim", "value": -254, "tt": 35 },
        "darker-any-release": { "type": "dim", "value": 0, "tt": 0 }
    }

    def __init__(self, bridge, apiKey):
        self.bridge = bridge
        self.apiKey = apiKey
        self.urlbase = "http://" + bridge + "/api/" + apiKey;
        self.refresh()

    def refresh(self):
        # read all data from the bridge
        tmp = requests.get(self.urlbase)
        if tmp.status_code != 200:
            raise "Cannot read bridge data"
        tmp.encoding = 'utf-8'
        self.__all = json.loads(tmp.text)
        self.__sensors = self.__all["sensors"]
        self.__sensors_idx = HueBridge.__make_index(self.__sensors, 'sensors')
        self.__lights = self.__all["lights"]
        self.__lights_idx = HueBridge.__make_index(self.__lights, 'lights')
        self.__groups = self.__all["groups"]
        self.__groups_idx = HueBridge.__make_index(self.__groups, 'groups', ['Group for wakeup'])
        self.__resourcelinks = self.__all["resourcelinks"]
        self.__resourcelinks_idx = HueBridge.__make_index(self.__resourcelinks, 'resourcelinks')
        self.__scenes = self.__all["scenes"]
        self.__scenes_idx = {}
        self.__groups_idx["All Lights"] = "0"
        for i in self.__scenes.keys():
            s = self.__scenes[i]
            n = s["name"].strip()
            g = None
            if not "group" in s:
                # try to find group with same lights
                lights = sorted(set(s["lights"]))
                for j in self.__groups.keys():
                    if sorted(set(self.__groups[j]["lights"])) == lights:
                        g = j
                        break
                if not g:
                    print("Warning: missing group ID for scene '" + n + "', lights", lights, "(ignoring)")
                    continue
            else:
                g = s["group"]
            if not g in self.__scenes_idx:
                self.__scenes_idx[g] = {}
            if n in self.__scenes_idx[g]:
                print("WARNING: Duplicate scene name '" + n + "' for group " + g + " ('" + self.__groups[g]["name"] + "'), IDs " + i + " and " + self.__scenes_idx[g][n])
            else:
                self.__scenes_idx[g][n] = i
        self.__rules = self.__all["rules"]
        self.__schedules = self.__all["schedules"]
        self.__schedules_idx = HueBridge.__make_index(self.__schedules, "schedules", [], False)
        
        self.__extinput = self.findSensor('ExternalInput')
        if not self.__extinput:
            print("Missing external input sensor, creating it")
            sensorData = {
                "state": {
                    "status": 1
                },
                "config": {
                    "on": True,
                    "reachable": True
                },
                "name": "ExternalInput",
                "type": "CLIPGenericStatus",
                "modelid": "GenericCLIP",
                "manufacturername": "Philips",
                "swversion": "1.0",
                "uniqueid": "external_input",
                "recycle": False
            }
            tmp = requests.post(self.urlbase + "/sensors", json=sensorData)
            if tmp.status_code != 200:
                raise Exception("Cannot create external input sensor")
            self.__extinput = json.loads(tmp.text)[0]["success"]["id"]
            print("Created external input sensor", self.__extinput)
        else:
            print("Using external input sensor ", self.__extinput)
        for i in self.__scenes_idx:
            print("Scenes for group", self.__groups[i]["name"] + ":", sorted(self.__scenes_idx[i].keys()))
        print("Sensors:", sorted(self.__sensors_idx.keys()))

        self.__prepare()

    def __prepare(self):
        """ Prepare class variables with actions to do on the bridge """
        self.__linkToDelete = None
        self.__rulesToDelete = []
        self.__rulesToCreate = []
        self.__sensorsToDelete = []
        self.__sensorsToCreate = []
        self.__schedulesToDelete = []
        self.__schedulesToCreate = []
        self.__groupsToAdd = []
        # scene lists are collected per group ID, similar to scene index
        self.__scenesToDelete = {}
        self.__scenesToCreate = {}
    
    def findLight(self, name):
        if name in self.__lights_idx:
            return self.__lights_idx[name]
        else:
            raise Exception("Light with name '" + name + "' not found")
    
    def findSensor(self, name):
        if name in self.__sensors_idx:
            return self.__sensors_idx[name]
        else:
            return None
    
    def findRulesForSensorID(self, sensorId):
        sensorAddr = "/sensors/" + sensorId + "/"
        idSet = []
        for rid in self.__rules.keys():
            for cond in self.__rules[rid]["conditions"]:
                if cond["address"].startswith(sensorAddr):
                    idSet.append(rid)
                    break
        return idSet
    
    def findRulesForExternalID(self, idList):
        sensorAddr = "/sensors/" + self.__extinput + "/state/status"
        idSet = []
        for rid in self.__rules.keys():
            for cond in self.__rules[rid]["conditions"]:
                if cond["address"] == sensorAddr and cond["operator"] == "eq" and cond["value"] in idList:
                    idSet.append(rid)
                    break
        return idSet
    
    @staticmethod
    def __make_index(array, tp, ignore = [], unique = True):
        index = {}
        for i in array.keys():
            s = array[i]
            n = s["name"].strip()
            if not n in ignore:
                if n in index:
                    if unique:
                        raise Exception("Duplicate " + tp + " name '" + n + "' in " + tp + ", indices " + index[n] + " and " + i)
                    else:
                        print("WARNING: Duplicate " + tp + " name '" + n + "' in " + tp + ", indices " + index[n] + " and " + i)
                else:
                    index[n] = i
        return index
    
    def __deleteSensor(self, sensorID):
        name = self.__sensors[sensorID]["name"]
        tmp = requests.delete(self.urlbase + "/sensors/" + sensorID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete sensor " + sensorID + "/" + name + ": " + tmp.text)
        del self.__sensors_idx[name]
        del self.__sensors[sensorID]
        print("Deleted sensor", sensorID, name)
        
    def __createSensor(self, sensorData):
        name = sensorData["name"]
        sensorData["name"] = name.strip()[0:32]
        sensorData["recycle"] = True
        tmp = requests.post(self.urlbase + "/sensors", json=sensorData)
        if tmp.status_code != 200:
            print("Data:", sensorData)
            raise Exception("Cannot create sensor " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            print("Data:", sensorData)
            raise Exception("Cannot sensor rule " + name + ": " + tmp.text)
        sensorID = result["success"]["id"]
        self.__sensors_idx[name] = sensorID
        sensorData["owner"] = self.apiKey
        self.__sensors[sensorID] = sensorData
        print("Created sensor", sensorID, name)
        return sensorID

    def __deleteRule(self, ruleID):
        name = self.__rules[ruleID]["name"]
        tmp = requests.delete(self.urlbase + "/rules/" + ruleID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete rule " + ruleID + "/" + name + ": " + tmp.text)
        del self.__rules[ruleID]
        print("Deleted rule", ruleID, name)
        
    def __createRule(self, ruleData):
        fullname = ruleData["name"].strip()
        name = fullname[0:28]
        while len(bytes(name, "utf-8")) > 28:
            name = name[:-1]
        if name != fullname:
            print("Data:", ruleData)
            print("WARNING: Shortening rule name '" + fullname + "' to '" + name + "'")
        ruleData["name"] = name
        ruleData["recycle"] = True
        tmp = requests.post(self.urlbase + "/rules", json=ruleData)
        if tmp.status_code != 200:
            print("Data:", ruleData)
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        ruleID = result["success"]["id"]
        ruleData["owner"] = self.apiKey
        self.__rules[ruleID] = ruleData
        print("Created rule", ruleID, name)
        return ruleID

    def __deleteSchedule(self, scheduleID):
        name = self.__schedules[scheduleID]["name"]
        tmp = requests.delete(self.urlbase + "/schedules/" + scheduleID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete schedule " + scheduleID + "/" + name + ": " + tmp.text)
        del self.__schedules[scheduleID]
        del self.__schedules_idx[name]
        print("Deleted schedule", scheduleID, name)

    def __createSchedule(self, scheduleData):
        fullname = scheduleData["name"].strip()
        name = fullname[0:32]
        if name != fullname:
            print("Data:", scheduleData)
            print("WARNING: Shortening schedule name '" + fullname + "' to '" + name + "'")
        scheduleData["name"] = name
        if not "recycle" in scheduleData:
            scheduleData["recycle"] = True
        tmp = requests.post(self.urlbase + "/schedules", json=scheduleData)
        if tmp.status_code != 200:
            print("Data:", scheduleData)
            raise Exception("Cannot create schedule " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create schedule " + name + ": " + tmp.text)
        scheduleID = result["success"]["id"]
        scheduleData["owner"] = self.apiKey
        self.__schedules[scheduleID] = scheduleData
        self.__schedules_idx[name] = scheduleID
        print("Created schedule", scheduleID, name)
        return scheduleID

    def __createScene(self, groupID, body):
        sceneName = body["name"]
        body["recycle"] = True
        lightstates = body["lightstates"]
        del body["lightstates"]
        r = requests.post(self.urlbase + "/scenes", json=body)
        if r.status_code != 200:
            print("Data:", body)
            raise Exception("Cannot create scene '" + sceneName + "', text=" + r.text)
        r.encoding = 'utf-8'
        res = json.loads(r.text)
        if not "success" in res[0]:
            print("Data:", body)
            raise Exception("Cannot create scene '" + sceneName + "', error: " + r.text)
        sceneID = res[0]["success"]["id"]
        body["owner"] = self.apiKey
        self.__scenes[sceneID] = body
        if not groupID in self.__scenes_idx:
            self.__scenes_idx[groupID] = {}
        self.__scenes_idx[groupID][sceneName] = sceneID
        for i in lightstates.keys():
            state = lightstates[i]
            r = requests.put(self.urlbase + "/scenes/" + sceneID + "/lights/" + str(i) + "/state", json=state)
            if r.status_code != 200:
                print("Data:", body)
                raise Exception("Cannot set up light " + str(i) + " in scene '" + sceneName + "', text=" + r.text)
            r.encoding = 'utf-8'
            res = json.loads(r.text)
            if not "success" in res[0]:
                print("Data:", body)
                raise Exception("Cannot set up light " + str(i) + " in scene '" + sceneName + "', error: " + r.text)

        print("Created scene", sceneID, sceneName, "for group", groupID)
        return sceneID

    def __deleteScene(self, groupID, sceneID):
        name = self.__scene_idx[groupID][sceneID]["name"]
        tmp = requests.delete(self.urlbase + "/scenes/" + sceneID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete scene " + sceneID + "/" + name + ": " + tmp.text)
        del self.__scene_idx[groupID][name]
        del self.__scenes[sceneID]
        print("Deleted scene", sceneID, name)

    def __deleteResourceLink(self, linkID):
        name = self.__resourcelinks[linkID]["name"]
        tmp = requests.delete(self.urlbase + "/resourcelinks/" + linkID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete resource link " + linkID + "/" + name + ": " + tmp.text)
        del self.__resourcelinks_idx[name]
        del self.__resourcelinks[linkID]
        print("Deleted resource link", linkID, name)

    def __ruleForSensorReset(self, v):
        """ Create rule for reset of sensor after timeout """
        if "timeout" in v:
            timeout = v["timeout"]
            name = v["name"]
            conditions = []
            if timeout.endswith("@off"):
                timeout = timeout[:-4]
                if not "group" in v:
                    raise Exception("Missing group parameter for @off timeout")
                groupID = self.__groups_idx[v["group"]]
                conditions = [
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "eq",
                        "value": "false"
                    }
                ]
            ruleData = {
                "name": name + "/timeout",
                "status": "enabled",
                "conditions": [
                    {
                        "address": "/sensors/${sensor:" + name + "}/state/status",
                        "operator": "ddx",
                        "value": "PT" + timeout
                    }
                ] + conditions,
                "actions": [
                    {
                        "address": "/sensors/${sensor:" + name + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 0
                        }
                    }
                ]
            }
            self.__rulesToCreate.append(ruleData)

    def __rulesForContact(self, v):
        """ Create rules for contact sensor """
        bindings = v["bindings"]
        openID = bindings["open"]
        closedID = bindings["closed"]
        name = v["name"]
        rules = []
        for i in [["open", openID, 0], ["closed", closedID, 1]]:
            ruleData = {
                "name": name + '/' + i[0],
                "status": "enabled",
                "conditions": [
                    {
                        "address": "/sensors/${sensor:" + name + "}/state/status",
                        "operator": "eq",
                        "value": str(1 - i[2])
                    },
                    {
                        "address": "/sensors/" + self.__extinput + "/state/status",
                        "operator": "eq",
                        "value": i[1]
                    },
                    {
                        "address": "/sensors/" + self.__extinput + "/state/lastupdated",
                        "operator": "dx",
                    }
                ],
                "actions": [
                    {
                        "address": "/sensors/${sensor:" + name + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": i[2]
                        }
                    },
                    {
                        "address": "/sensors/" + self.__extinput + "/state",
                        "method": "PUT",
                        "body": {
                            "status": 1
                        }
                    }
                ]
            }
            rules.append(ruleData)
        self.__rulesToCreate += rules

    def __replaceVariable(self, match):
        tp = match.group(1)
        name = match.group(2)
        if tp == "sensor":
            return self.__sensors_idx[name]
        elif tp == "group":
            return self.__groups_idx[name]
        elif tp == "scene":
            smatch = SCENE_PATTERN.search(name)
            group = smatch.group(1)
            scene = smatch.group(2)
            gid = self.__groups_idx[group]
            return self.__scenes_idx[gid][scene]
        elif tp == "schedule":
            return self.__schedules_idx[name]
        else:
            raise Exception("Unknown variable type '" + tp + "' in replacement for '" + name + "'")
        
    def __parseCommon(self, desc, template = {}):
        """ Parse common settings and return a state object """
        state = dict(template)
        if "state" in desc:
            state["state"] = desc["state"]
        if "stateUse" in desc:
            state["stateUse"] = desc["stateUse"]
        else:
            state["stateUse"] = "primary"
        if "group" in desc:
            state["group"] = desc["group"]
        return state
    
    def __redirectRule(self, binding, name, ref, state, conditions, actions):
        """ Create redirect rule """
        value = binding["value"]
        resetActions = [
                {
                    "address": "/sensors/" + self.__extinput + "/state",
                    "method": "PUT",
                    "body": {
                        "status": int(value)
                    }
                }
            ]
        self.__rulesToCreate.append({
            "name": name + "/" + ref + "=" + value,
            "status": "enabled",
            "conditions": conditions,
            "actions": actions + resetActions
        })
        
    def __singleSceneRules(self, config, name, state, conditions, actions):
        """ Rules for a single item in scene/multi-scene config """
        scene = config["scene"]
        group = state["group"]

        groupID = self.__groups_idx[group]
        sceneActions = []
        if scene == "off":
            sceneActions = [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "on": False
                    }
                }
            ]
        elif scene == "dim":
            value = config["value"]
            body = { "bri_inc" : value }
            if "tt" in config:
                body["transitiontime"] = config["tt"]
            sceneActions = [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": body
                }
            ]
        else:
            sceneID = self.__scenes_idx[groupID][scene]
            sceneActions = [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "scene": sceneID
                    }
                }
            ]
        self.__rulesToCreate.append({
            "name": name,
            "status": "enabled",
            "conditions": conditions,
            "actions": actions + sceneActions
        })
        
    def __sceneRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for switching to a scene """
        state = self.__parseCommon(binding, state)
        configs = []
        if "configs" in binding:
            configs = binding["configs"]
            if "value" in binding:
                raise Exception("Either configs or value must be specified for scene, but not both")
        elif "value" in binding:
            # shortcut for single-scene binding (value instead of configs)
            configs = [ {"scene": binding["value"]} ]
        else:
            raise Exception("Either configs or value must be specified for scene")
        index = 0
        # if more than single config, we have a multistate switch, either time-based or multi-sstate or combined
        multistate = len(configs) > 1
        if multistate and not "state" in state and not "times" in binding:
            raise Exception("Missing state configuration for a multistate config w/o times for " + name + "/" + ref)
        secondaryState = state["stateUse"] == "secondary";

        resetstateactions = []
        if "state" in state:
            resetstateactions = [
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": 0 }
                }
            ]
        if "setstate" in binding:
            if not "state" in state:
                raise Exception("Missing state configuration to be able to set state of the switch via setstate")
            if multistate:
                raise Exception("Setting state via setstate is mutually exclusive with multistate scene")
            idx = binding["setstate"]
            if secondaryState:
                idx = -idx
            resetstateactions = [
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": idx }
                }
            ]

        for config in configs:
            print("Process",name,index,config)
            cname = name + "/" + ref;
            nextIndex = index + 1
            prevIndex = index
            if "times" in binding:
                # we need to distinguish between time-related start of sequence or wraparound
                if index == 0:
                    prevIndex = len(configs)
            elif index == len(configs) - 1:
                nextIndex = 0

            if multistate and "state" in state:
                cname = cname + "/" + str(index)
                if prevIndex != 0:
                    # rule based on previous state (for multiple presses)
                    stateCond = [
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state/status",
                            "operator": "eq",
                            "value": str(-prevIndex if secondaryState else prevIndex)
                        }
                    ]
                    stateAction = [
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state",
                            "method": "PUT",
                            "body": {
                                "status": -nextIndex if secondaryState else nextIndex
                            }
                        }
                    ]
                    self.__singleSceneRules(config, cname, state, stateCond + conditions, stateAction + actions)
                
            if "times" in binding:
                # multiple time-based rules to turn on scenes, get the one for this index
                times = binding["times"]
                tidx = 1
                for timerange in times:
                    # time indices are 1-based, therefore add 1
                    if times[timerange] == index + 1:
                        stateCond = [
                            {
                                "address": "/config/localtime",
                                "operator": "in",
                                "value": timerange
                            }
                        ]
                        stateAction = resetstateactions
                        if multistate and "state" in state:
                            # only trigger if state not yet set
                            stateCond += [
                                {
                                    "address": "/sensors/${sensor:" + state["state"] + "}/state/status",
                                    "operator": "gt" if secondaryState else "lt",
                                    "value": str(-1 if secondaryState else 1)
                                }
                            ]
                            stateAction = [
                                {
                                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                                    "method": "PUT",
                                    "body": {
                                        "status": -nextIndex if secondaryState else nextIndex
                                    }
                                }
                            ]
                        self.__singleSceneRules(config, cname + "/T" + str(tidx), state, conditions + stateCond, stateAction + actions)
                    tidx = tidx + 1
            elif index == 0:
                if multistate and "state" in state:
                    # single rule to turn scene #0 if no state set
                    stateCond = [
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state/status",
                            "operator": "gt" if secondaryState else "lt",
                            "value": str(-1 if secondaryState else 1)
                        }
                    ]
                    stateAction = [
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state",
                            "method": "PUT",
                            "body": {
                                "status": -1 if secondaryState else 1
                            }
                        }
                    ]
                    self.__singleSceneRules(config, cname + "/in", state, conditions + stateCond, actions + stateAction)
                else:
                    # single config, no additional conditions
                    self.__singleSceneRules(config, cname, state, conditions, resetstateactions + actions)

            if "timeout" in config:
                # create extra rule to turn off light in this state
                timeout = "PT" + config["timeout"]
                stateCond = None
                group = state["group"]
                groupID = self.__groups_idx[group]
                if "state" in state and multistate:
                    stateCond = [
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state/status",
                            "operator": "eq",
                            "value": str(-nextIndex if secondaryState else nextIndex)
                        },
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state/lastupdated",
                            "operator": "ddx",
                            "value": timeout
                        }
                    ]
                elif not multistate:
                    # single-state, simply turn off after a timeout
                    print("WARNING: single-state timeout on '" + name + "' will not be interrupted by changing light state by pressing switch again")
                    stateCond = [
                        {
                            "address": "/groups/" + groupID + "/state/any_on",
                            "operator": "ddx",
                            "value": timeout
                        }
                    ]
                else:
                    # multistate, based on time
                    raise Exception("Support for time-based multistate timeout w/o state variable not implemented, add state variable to '" + name + "'")

                rule = {
                    "name": cname + "/TO" + str(index),
                    "conditions": stateCond + [{
                            "address": "/groups/" + groupID + "/state/any_on",
                            "operator": "eq",
                            "value": "true"
                        }],
                    "actions": resetstateactions + [
                        {
                            "address": "/groups/" + groupID + "/action",
                            "method": "PUT",
                            "body": {
                                "on": False
                            }
                        }
                    ]
                }
                self.__rulesToCreate.append(rule)

            index = index + 1
        
    def __lightRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for switching a single light """
        state = self.__parseCommon(binding, state)
        lightID = self.findLight(binding["light"])
        action = binding["action"]
        if action == "on" or action == "off":
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/state",
                    "method": "PUT",
                    "body": {
                        "on": True if action == "on" else False
                    }
                }
            ]

            rule = {
                "name": name + "/" + ref + "/" + action,
                "status": "enabled",
                "conditions": conditions,
                "actions": actions + lightActions
            }
            self.__rulesToCreate.append(rule)
        elif action == "toggle":
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/state",
                    "method": "PUT",
                    "body": { "on": True }
                }
            ]
            rule = {
                "name": name + "/" + ref + "/on",
                "status": "enabled",
                "conditions": conditions + [
                    {
                        "address": "/lights/" + lightID + "/state/on",
                        "operator": "eq",
                        "value": "false"
                    }
                ],
                "actions": actions + lightActions
            }
            self.__rulesToCreate.append(rule)
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/state",
                    "method": "PUT",
                    "body": { "on": False }
                }
            ]
            rule = {
                "name": name + "/" + ref + "/off",
                "status": "enabled",
                "conditions": conditions + [
                    {
                        "address": "/lights/" + lightID + "/state/on",
                        "operator": "eq",
                        "value": "true"
                    }
                ],
                "actions": actions + lightActions
            }
            self.__rulesToCreate.append(rule)
        else:
            raise Exception("Invalid action '" + action + "', expected on/off/toggle")

    def __dimRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for dimming or lightening a group """
        state = self.__parseCommon(binding, state)
        groupID = self.__groups_idx[state["group"]]
        value = binding["value"]
        tt = 9
        if "tt" in binding:
            tt = binding["tt"]
        body = { "bri_inc" : value }
        if tt != 0:
            body["transitiontime"] = tt
        rule = {
            "name": name + "/" + ref,
            "status": "enabled",
            "conditions": conditions,
            "actions": actions + [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": body
                }
            ]
        }
        self.__rulesToCreate.append(rule)

    def __createRulesForAction(self, binding, name, ref, state, conditions = [], actions = [], resetstateactions = []):
        if type(binding) == list:
            # create rule for each action
            for item in binding:
                self.__createRulesForAction(item, name, ref, state, conditions, actions, resetstateactions)
            # NOTE: This can be optimized, since conditions are typically the same, just actions need to be concatenated.
            # For example, it would be possible to see which rules were added, group them by same conditions
            # and concatenate their actions. Or to refactor called methods to return actions only (except for
            # multi-rule actions).
            return

        state = self.__parseCommon(binding, state)
        tp = binding["type"]
        if "state" in state and len(resetstateactions) == 0:
            resetstateactions = [
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": 0 }
                }
            ]
        if tp == "redirect":
            # NOTE: explicitly ignore passed actions, since they reset external input to 1, when called for external
            # The only exception is motion sensor, which needs to explicitly set state.
            self.__redirectRule(binding, name, ref, state, conditions, resetstateactions)
        elif tp == "scene":
            self.__sceneRules(binding, name, ref, state, conditions, actions)
        elif tp == "off":
            self.__sceneRules(OFF_BINDING, name, ref, state, conditions, actions)
        elif tp == "light":
            self.__lightRules(binding, name, ref, state, conditions, resetstateactions + actions)
        elif tp == "dim":
            self.__dimRules(binding, name, ref, state, conditions, resetstateactions + actions)
        else:
            raise Exception("Invalid binding type '" + tp + "'")
    
    @staticmethod
    def __mapButton(button):
        """ Map button from name to ID """
        if button in BUTTON_MAP:
            return BUTTON_MAP[button]
        else:
            return button
        
    def __rulesForSwitch(self, desc):
        """ Create rules for switch buttons """
        state = self.__parseCommon(desc)
        switchName = desc["name"]
        bindings = desc["bindings"]
        switchID = self.findSensor(switchName)
        if not switchID:
            raise Exception("Switch '" + switchName + "' not found")
        self.__rulesToDelete += self.findRulesForSensorID(switchID) # gets rid of old rules for this switch
        for button in bindings.keys():
            binding = bindings[button]
            conditions = [
                {
                    "address": "/sensors/${sensor:" + switchName + "}/state/lastupdated",
                    "operator": "dx"
                }
            ]
            if button == "brighter-any-release":
                conditions += [
                    {
                        "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                        "operator": "gt",
                        "value": "2001"
                    },
                    {
                        "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                        "operator": "lt",
                        "value": "2004"
                    }
                ]
            elif button == "darker-any-release":
                conditions += [
                    {
                        "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                        "operator": "gt",
                        "value": "3001"
                    },
                    {
                        "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                        "operator": "lt",
                        "value": "3004"
                    }
                ]
            else:
                conditions.append(
                    {
                        "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                        "operator": "eq",
                        "value": HueBridge.__mapButton(button)
                    }
                )
            self.__createRulesForAction(binding, switchName, button, state, conditions, [])
        
    def __rulesForExternal(self, desc):
        """ Create rules for external input """
        state = self.__parseCommon(desc)
        bindings = desc["bindings"]
        name = desc["name"]
        self.__rulesToDelete += self.findRulesForExternalID(bindings.keys()) # get rid of old rules for bindings
        actions = [
            {
                "address": "/sensors/" + self.__extinput + "/state",
                "method": "PUT",
                "body": {
                    "status": 1
                }
            }
        ]
        for extID in bindings.keys():
            binding = bindings[extID]
            conditions = [
                {
                    "address": "/sensors/" + self.__extinput + "/state/lastupdated",
                    "operator": "dx"
                },
                {
                    "address": "/sensors/" + self.__extinput + "/state/status",
                    "operator": "eq",
                    "value": extID
                }
            ]
            self.__createRulesForAction(binding, name, extID, state, conditions, actions)
                    
    def __rulesForMotion(self, desc):
        """
        Create rules for motion sensor 
        
        Motion sensor actually uses three sensors:
           - motion sensor proper
           - light sensor
           - companion sensor to store state
        
        State sensor can have following states:
           - 0 and -1: the motion sensor is armed and will turn on the light
           - 1: the light is on, we are in timeout phase
           - 2: the light is in dimmed state
           - 3: the light is on and updates are blocked by door contact
           - -2: set by turning associated group off not by sensor itself, sensor doesn't react in state -2 until timeout
        
        Following states and transitions are used:
            - -2: off by switch
            - -1: off by sensor
            - 0: initial state, no motion, lights are off
                rule(1): motion detected in dark: turn on lights and switch to state 2
                    turning lights on and moving to state 2 when both of them detected. However, it doesn't
                    This should be possible with a single rule just checking state of presence and dark,
                    work correctly, so currently we have 3 rules with dx on presence, dark and state change.
                [rule(2-3): unused, previously they were used for ddx on individual variables]
            - 1: lights on, but no motion detected:
                rule(4): motion detected and lights on switches to state 2
                rule(5): timer starts after entering state 1, after a timeout:
                    if lights are on and state is still 1 and door contact open (if used):
                    dim lights and enter state 3
            - 2: motion detected, lights are on
                rule(6): no motion detected in state 2:
                    switch to state 1 (rule(4) switches back to state 2 upon motion)
                Here, we should not react on dx operator, but simple check for state and presence, since
                switch might switch to state 2, but that wouldn't trigger any timeout if noone comes into
                the room. When using just a plain check, we'd fall back to state 1 and start timeout,
                even if noone enters the room.
            - 3: light is dimmed:
                rule(7): timer starts after entering state 3, after a timeout:
                    if state is still 3, turn lights off and enter state -1 (off by sensor)
                rule(8): if motion is detected in state 3: recover light state and change state to 2

        Handling of turning on/off via switch or app:
            rule(9): after manually switched on, change state to 2 (which will transition to 1 upon no motion)
            rule(10): after manually switched off when door open, change state to -2
            rule(11): after off timeout, change state -2->-1 to allow sensor to react

        If a door contact sensor is used:
            when door contact closes (state 1-3):
                rule(12): check after a 16s timeout (motion sensor reports non-presence at the latesst after 15s):
                    if no motion is detected, door still closed and state is still >0 turn lights off and go to state 0 (or -1?)
            when door contact goes to open:
                rule(13a): switch to state 2, independent of motion (rule(6) will switch to state 1)
                    rule(13b): if dimmed, undim the light
            rule(14): after manually switched on when door closed, change to state 2 (will fall to 1 on no motion)
                and set door closed again to force reevaluation via rule(12)

        Motion sensor supports following bindings:
            - "on" - turn on the lights
            - "off" - turn off the lights (default: all lights in the group off)
            - "dim" - what to do on timeout (default: dim all lights in the group by 50%)
            - "recover" - what to do when motion detected in dimmed state (default: recover scene before dimming)
        """

        state = self.__parseCommon(desc)
        name = desc["name"]
        if not "group" in state:
            raise Exception("No group set for motion sensor '" + name + "'")
        groupName = state["group"]
        groupID = self.__groups_idx[groupName]
        bindings = desc["bindings"]
        stateSensorName = name + " state"
        sensorID = self.findSensor(name)
        if not sensorID:
            raise Exception("Sensor '" + name + "' not found")
        if self.__sensors[sensorID]["type"] != "ZLLPresence":
            raise Exception("Sensor '" + name + "' is not a presence sensor")
        self.__rulesToDelete += self.findRulesForSensorID(sensorID)
        self.__prepareSensor({
            "type": "state",
            "name": stateSensorName
        })
        sensorAddress = self.__sensors[sensorID]["uniqueid"][0:24]
        lightSensorID = None
        for key in self.__sensors.keys():
            s = self.__sensors[key]
            if s["type"] != "ZLLLightLevel":
                continue
            if s["uniqueid"][0:24] == sensorAddress:
                lightSensorID = key
                break
        if not lightSensorID:
            raise Exception("Light level sensor for '" + name + "' not found")
        
        # recovery scene handling
        sceneName = name + " recover"
        self.__prepareDeleteScene(groupID, sceneName)
        sceneID = None
        if not "recover" in bindings:
            # create new scene for the group to store light state to recover, but only if needed
            body = {
                "name": sceneName,
                "lights": self.__groups[groupID]["lights"]
                #"group": groupID
            }
            if not groupID in self.__scenesToCreate:
                self.__scenesToCreate[groupID] = []
            self.__scenesToCreate[groupID].append(body)
            sceneID = "${scene:" + groupName + ":" + sceneName + "}"

        onactions = None
        offactions = None
        dimactions = None
        dimstatecopy = state
        recoveractions = None
        for act in bindings.keys():
            binding = bindings[act]
            if act == "on":
                onactions = binding
            elif act == "off":
                offactions = binding
            elif act == "dim":
                dimactions = binding
                # create copy of the state w/o "state" key, since we don't want to modify switch state here
                dimstatecopy = deepcopy(state)
                dimstatecopy.pop("state", None)
            elif act == "recover":
                recoveractions = binding
            else:
                raise Exception("Unsupported binding '" + act + "' for motion sensor")
        if isinstance(recoveractions, str):
            if recoveractions == "on":
                recoveractions = onactions
            else:
                raise Exception("Unsupported recover action redirect '" + recoveractions + "' for motion sensor")

        contactName = None
        contactOpenCond = []
        contactClosedCond = []
        if "contact" in desc:
            contactName = desc["contact"]
            contactOpenCond = [
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "0"
                }]
            contactClosedCond = [
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                }]


        # handling for states <=0
        
        # rule(1): motion detected in dark and lights off: turn on lights and switch to state 1
        conditions = [
            {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "eq",
                "value": "true"
            },
            {
                "address": "/sensors/" + lightSensorID + "/state/dark",
                "operator": "eq",
                "value": "true"
            },
            # NOTE: react only if not blocked by switch
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "gt",
                "value": "-2"
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "lt",
                "value": "1"
            },
            # NOTE: only turn on if it was off at least for a second. This prevents
            # a situation where light on redirects to a rule is after light off rule,
            # effectively making turning light off impossible.
            {
                "address": "/groups/${group:" + groupName + "}/state/any_on",
                "operator": "stable",
                "value": "PT00:00:01"
            }
        ]
        actions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": 2
                }
            }
        ]
        if "state" in state:
            # reset associated switch sensor state before turning on lights (typically turned on via redirect)
            actions.append(
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": 0 }
                }
            )
        # Previously, we created 3 rules with dx on relevant variables, but this is not really
        # necessary, since the rule will be evaluated when any of the variables changes.
        #for i in [
        #    ["pres.on", {
        #        "address": "/sensors/" + sensorID + "/state/presence",
        #        "operator": "dx"
        #    }],
        #    ["dark.on", {
        #        "address": "/sensors/" + lightSensorID + "/state/dark",
        #        "operator": "dx"
        #    }],
        #    ["stat.on", {
        #        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
        #        "operator": "dx",
        #    }]
        #]:
        #    cname = i[0]
        #    condition = i[1]
        #    if onactions:
        #        self.__createRulesForAction(onactions, name, cname, state, conditions + [condition], actions)
        #    else:
        #        self.__rulesToCreate.append({
        #            "name": name + "/" + cname,
        #            "conditions": conditions + [condition],
        #            "actions": actions
        #        })
        if onactions:
            self.__createRulesForAction(onactions, name, "on", state, conditions, [], actions)
        else:
            self.__rulesToCreate.append({
                "name": name + "/on",
                "conditions": conditions,
                "actions": actions
            })

        # handling for state 1
        #
        # Note: no check on actual light on, since sometimes the light state is not reliable.
        # We simply assume state 1 has lights on.

        # rule(4): motion detected and lights on switches to state 2
        self.__rulesToCreate.append({
            "name": name + "/motion",
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "true"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                }
                # NOTE: no dx/ddx operator here, it has to switch if conditions are met
                # (e.g., switch turned on or door goes to open)
            ],
            "actions": [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 2
                    }
                }
            ]
        })

        # rule(5): timer starts after entering state 1, after a timeout:
        #          if lights are on (assumed) and state is still 1 and door contact open
        #          dim lights and enter state 3
        conditions = [
            {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "eq",
                "value": "false"
            },
            # ddx on last update of state sensor instead of presence sensor to turn off
            # also after switching light on w/o movement
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/lastupdated",
                "operator": "ddx",
                "value": "PT" + desc["timeout"]
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "eq",
                "value": "1"
            }
        ] + contactOpenCond
        actionstodim = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": 3
                }
            }
        ]
        if not recoveractions:
            # we need to store light state, so we can recover it on recover action
            actionstodim.append({
                "address": "/scenes/" + sceneID,
                "method": "PUT",
                "body": {
                    "storelightstate": True
                }
            })
        if not dimactions:
            actionstodim.append({
                "address": "/groups/" + groupID + "/action",
                "method": "PUT",
                "body": {
                    "bri_inc": -128 # dim to half
                }
            })
        # TODO: needed?
        #if "state" in state:
        #    # reset associated switch sensor state before using the action (typically turned on via redirect)
        #    actionstodim.append(
        #        {
        #            "address": "/sensors/${sensor:" + state["state"] + "}/state",
        #            "method": "PUT",
        #            "body": { "status": 0 }
        #        }
        #    )
        if dimactions:
            self.__createRulesForAction(dimactions, name, "dim", dimstatecopy, conditions, actionstodim)
        else:
            self.__rulesToCreate.append({
                "name": name + "/dim",
                "conditions": conditions,
                "actions": actionstodim
            })
        if "contact" in desc and "closedtimeout" in desc:
            # rule(5b): Requested timeout when the door is closed and light was turned on permanently.
            # This is a safety net if door contact breaks.
            conditions = [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                # ddx on last update of state sensor instead of presence sensor to turn off
                # also after switching light on w/o movement
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/lastupdated",
                    "operator": "ddx",
                    "value": "PT" + desc["closedtimeout"]
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                }
            ] + contactClosedCond
            if dimactions:
                self.__createRulesForAction(dimactions, name, "dim", dimstatecopy, conditions, actionstodim)
            else:
                self.__rulesToCreate.append({
                    "name": name + "/dim.closed",
                    "conditions": conditions,
                    "actions": actionstodim
                })

        # handling for state 2: motion detected, lights are on
        
        # rule(6): no motion detected in state 2:
        #            switch to state 1 (if lights still on, rule(4) switches back to state 2 upon motion)
        self.__rulesToCreate.append({
            "name": name + "/no.pres",
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "2"
                }
            ],
            "actions": [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 1
                    }
                }
            ]
        })
                
        # hanlding for state 3: light is dimmed
        
        # rule(7): timer starts after entering state 3, after a timeout:
        #            if state is still 3, turn lights off and enter state -1 (off by sensor)
        dimtime = "PT00:00:20"
        if "dimtime" in desc:
            dimtime = "PT" + desc["dimtime"]
        conditions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/lastupdated",
                "operator": "ddx",
                "value": dimtime
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "eq",
                "value": "3"
            }
        ]
        actions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": -1
                }
            }
        ]
        if "state" in state:
            # reset associated switch sensor state before turning off lights
            actions.append(
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": 0 }
                }
            )
        if offactions:
            # explicit off action specified
            self.__createRulesForAction(offactions, name, "off", state, conditions, actions)
        else:
            # no off action, add default one (group off)
            self.__rulesToCreate.append({
                "name": name + "/off",
                "conditions": conditions,
                "actions" : actions + [
                    {
                        "address": "/groups/" + groupID + "/action",
                        "method": "PUT",
                        "body": {
                            "on": False
                        }
                    },
                ]
            })

        #  rule(8): if motion is detected in state 3: recover light state and change state to 2
        conditions = [
            {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "eq",
                "value": "true"
            },
            {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "dx"
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "eq",
                "value": "3"
            }
        ]
        actions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": 2
                }
            }
        ]
        if recoveractions:
            if "state" in state:
                # reset associated switch sensor state before turning on lights (typically turned on via redirect)
                actions.append(
                    {
                        "address": "/sensors/${sensor:" + state["state"] + "}/state",
                        "method": "PUT",
                        "body": { "status": 0 }
                    }
                )
            self.__createRulesForAction(recoveractions, name, "recover", state, conditions, [], actions)
        else:
            self.__rulesToCreate.append({
                "name": name + "/recover",
                "conditions": conditions,
                "actions": [{
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "scene": sceneID
                    }
                }] + actions
            })

        # Handling of turning on/off via switch or app:

        # rule(9): after manually switched on, change state to 2 (which will transition to 1 upon no motion)
        self.__rulesToCreate.append(
            {
                "name": name + "/switch.on",
                "actions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 2
                        }
                    }
                ],
                "conditions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "lt",
                        "value": "2"
                    },
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "eq",
                        "value": "true"
                    },
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "dx"
                    }
                ] + contactOpenCond
            }
        )
        
        # rule(10): after manually switched off, change state to -2 after delay of 1s
        self.__rulesToCreate.append(
            {
                "name": name + "/switch.off",
                "actions" : [
                    {
                        "address": "/schedules/${schedule:" + stateSensorName + "}",
                        "method": "PUT",
                        "body": {
                            "status": "enabled"    # start 1s timer
                        }
                    }
                ],
                "conditions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "gt",
                        "value": "-1"
                    },
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "eq",
                        "value": "false"
                    },
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "dx"
                    }
                ] 
            }
        )
        self.__schedulesToCreate.append(
            {
                "name": stateSensorName,
                "description": stateSensorName + " (reset after off)",
                "status": "disabled",
                "autodelete": False,
                "localtime": "PT00:00:01",
                "command": {
                    "address": "/api/" + self.apiKey + "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": -2    # this disables the sensor for some time
                    }
                }
            }
        )
        
        # Handling for state -2 for timeouts on switch on/off
        # rule(11): after off timeout, change state -2->-1
        offtimeout = "PT00:00:30"
        if "offtimeout" in desc:
            offtimeout = "PT" + desc["offtimeout"]
        self.__rulesToCreate.append(
            {
                "name": name + "/blocked",
                "actions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": -1
                        }
                    }
                ],
                "conditions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "eq",
                        "value": "-2"
                    },
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/lastupdated",
                        "operator": "ddx",
                        "value": offtimeout
                    }
                ]
            }
        )
        

        # additional handling for door contact
        
        if "contact" in desc:
            # Add rules to handle door contact.
            #
            # When the door is closed and motion has been detected after the door is closed,
            # then don't react until door is open again (this is handled in off rule 4 above).
            #
            # If no motion has been detected after door is closed, then turn off light.
            #
            # The sensor sends a no-presence signal after 10 seconds of no-presence detection.
            # So check after 11 seconds after closing doors whether there is presence or not.

            contactName = desc["contact"]

            # when door contact goes to closed:

            # rule(12): check after a 16s timeout:
            #    if no motion is detected and state is still 3 turn lights off and keep state 3
            closedchecktime = "PT00:00:16"
            if "closedchecktime" in desc:
                closedchecktime = "PT" + desc["closedchecktime"]
            actions = []
            conditions = [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "gt",
                    "value": "0"
                },
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                },
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/lastupdated",
                    "operator": "ddx",
                    "value": closedchecktime
                }
            ]
            if dimactions:
                self.__createRulesForAction(dimactions, name, "clo.off", dimstatecopy, conditions, actionstodim)
            else:
                self.__rulesToCreate.append({
                    "name": name + "/clo.off",
                    "conditions": conditions,
                    "actions": actionstodim
                })

            # rule(14): after manually switched on when door closed, set door closed again to force reevaluation via rule(12)
            conditions = [
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "true"
                },
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "dx"
                }
            ] + contactClosedCond
            self.__rulesToCreate.append({
                "name": name + "/switch.on.closed",
                "conditions": conditions,
                "actions" : actions + [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 2
                        }
                    },
                    {
                        "address": "/sensors/${sensor:" + contactName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 1,
                        }
                    },
                ]
            })

            # rule(13): when door contact goes to open
            actions = [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 2
                    }
                }
            ]
            conditions = [
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "0"
                },
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "dx"
                }
            ]
            self.__rulesToCreate += [
                # rule(13a): switch to state 2, independent of motion (rule(6) will switch to state 1)
                {
                    "name": name + "/open",
                    "actions" : actions,
                    "conditions" : conditions + [
                        {
                            "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                            "operator": "gt",
                            "value": "0"
                        },
                        {
                            "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                            "operator": "lt",
                            "value": "3"
                        }
                    ]
                }
            ]
            # rule(13b): switch to state 2 and recover light, independent of motion (rule(6) will switch to state 1)
            conditions = conditions + [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "3"
                }
            ]
            if recoveractions:
                if "state" in state:
                    # reset associated switch sensor state before turning on lights (typically turned on via redirect)
                    actions.append(
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state",
                            "method": "PUT",
                            "body": { "status": 0 }
                        }
                    )
                self.__createRulesForAction(recoveractions, name, "recover.open", state, conditions, [], actions)
            else:
                self.__rulesToCreate.append({
                    "name": name + "/recover.open",
                    "conditions": conditions,
                    "actions": [{
                        "address": "/groups/" + groupID + "/action",
                        "method": "PUT",
                        "body": {
                            "scene": sceneID
                        }
                    }] + actions
                })

    def __updateReferences(self, obj):
        if type(obj) is list:
            for i in obj:
                # call for each list element
                self.__updateReferences(i)
        elif type(obj) is dict:
            for i in obj.keys():
                value = obj[i]
                if type(value) is str:
                    # tokenize on ${name:value}
                    replacement = VAR_PATTERN.sub(lambda match: self.__replaceVariable(match), value)
                    if replacement != value:
                        #print "Replaced:", value, "=>", replacement 
                        obj[i] = replacement
                else:
                    # call recursively for sub-dicts
                    self.__updateReferences(value)

    def __prepareSensor(self, v, wakeup = False):
        name = v["name"]
        s = self.findSensor(name)
        if s:
            if self.__sensors[s]["type"] != ("CLIPGenericFlag" if wakeup else "CLIPGenericStatus"):
                raise Exception("Sensor '" + name + "' is not a generic status sensor")
            self.__sensorsToDelete.append(s)
            self.__rulesToDelete += self.findRulesForSensorID(s)
        sensorData = {
            "state": {
                "status": 0
            },
            "config": {
                "on": True,
                "reachable": True
            },
            "name": name,
            "type": "CLIPGenericStatus",
            "modelid": "GenericCLIP",
            "manufacturername": "Philips",
            "swversion": "1.0",
            "uniqueid": name
        }
        if wakeup:
            sensorData["type"] = "CLIPGenericFlag"
            sensorData["modelid"] = "WAKEUP"
            sensorData["swversion"] = "A_1801260942"
            sensorData["uniqueid"] = "L_04_" + name
            del sensorData["state"]["status"]
            sensorData["state"]["flag"] = False
        self.__sensorsToCreate.append(sensorData)
        self.__ruleForSensorReset(v)
        if v["type"] == "contact":
            self.__rulesForContact(v)

    def __prepareDeleteScene(self, groupID, sceneName):
        if groupID in self.__scenes_idx:
            if sceneName in self.__scenes_idx[groupID]:
                # remove old scene, if if exists
                if not groupID in self.__scenesToDelete:
                    self.__scenesToDelete[groupID] = []
                self.__scenesToDelete[groupID].append(self.__scenes_idx[groupID][sceneName])

    def __prepareDeleteSchedule(self, scheduleName):
        if scheduleName in self.__schedules_idx:
            self.__schedulesToDelete.append(self.__schedules_idx[scheduleName])

    def __min_to_reltime(self, mins):
        """ Create interval from minutes in form PTHH:MM:SS """
        hrs = int(mins / 60)
        mins -= hrs * 60
        return "PT{:02d}:{:02d}:00".format(hrs, int(mins))

    def __rulesForWakeup(self, w):
        """ Create rules for wakeup timer """

        # parameters
        name = w["name"]
        group = w["group"]
        duration = 20
        starttime = w["start"]
        if "duration" in w:
            duration = w["duration"]
            if duration <= 1 or duration > 60:
                raise Exception("Duration must be in range of [2..60] minutes")
        offtime = 60
        if "offtime" in w:
            offtime = w["offtime"]
            if offtime < 1 or offtime > 240:
                raise Exception("Off time must be in range of [1..240] minutes, otherwise it doesn't make sense")
        offtimedelay = self.__min_to_reltime(offtime + duration)

        uniqueid = "L_04_" + "03445"    # name    TODO unique ID

        # names
        sensorname = "Wake up " + name
        sensoraddr = "/sensors/${sensor:" + sensorname + "}"
        startscenename = "Wake Up init"    # Initial scene to play for the first minute (minimum brightness)
        endscenename = "Wake Up end"       # End scene to slowly transition to (maximum brightness)
        schedule1name = "Wake up " + name
        schedule2name = uniqueid
        startrulename = uniqueid + "_Start"
        endrulename = "Wake up 9.end"   # TODO

        groupid = self.__groups_idx[group]
        gdata = self.__groups[groupid]
        lights = gdata["lights"]

        self.__prepareSensor({
            "type": "state",
            "name": sensorname
        }, True)
        self.__prepareDeleteScene(groupid, startscenename)
        self.__prepareDeleteScene(groupid, endscenename)
        self.__prepareDeleteSchedule(schedule1name)
        self.__prepareDeleteSchedule(schedule2name)

        startscene = {
            "name": startscenename,
            "lights": lights,
            #"locked": True,
            "lightstates": {}
        }
        endscene = {
            "name": endscenename,
            "lights": lights,
            #"locked": True,
            "lightstates": {}
        }
        for light in lights:
            startscene["lightstates"][light] = {
                "on": True,
                "bri": 1,
                "ct": 447
            }
            endscene["lightstates"][light] = {
                "on": True,
                "bri": 254,
                "ct": 447,
                "transitiontime": int((duration - 1) * 600)
            }

        schedule1 = {
            "name": schedule1name,
            "description": uniqueid + "_start wake up",
            "command": {
                "address": "/api/" + self.apiKey + "/sensors/${sensor:" + sensorname + "}/state",
                "body": { "flag": True },
                "method": "PUT"
            },
            "localtime": starttime,
            "status": "disabled"
        }

        schedule2 = {
            "name": schedule2name,
            "description": uniqueid + "_trigger end scene",
            "command": {
                "address": "/api/" + self.apiKey + "/groups/0/action",
                "body": {
                    "scene": "${scene:" + group + ":" + endscenename + "}"
                },
                "method": "PUT"
            },
            "localtime": "PT00:01:00",
            "status": "disabled",
            "autodelete": False
        }

        startrule = {
            "name": startrulename,
            "status": "enabled",
            "conditions": [
                {
                    "address": "/sensors/${sensor:" + sensorname + "}/state/flag",
                    "operator": "eq",
                    "value": "true"
                }
            ],
            "actions": [
                {
                    "address": "/schedules/${schedule:" + schedule2name + "}",
                    "method": "PUT",
                    "body": { "status": "enabled" }
                },
                {
                    "address": "/groups/${group:" + group + "}/action",
                    "method": "PUT",
                    "body": { "scene": "${scene:" + group + ":" + startscenename +  "}" }
                }
            ]
        }

        endrule = {
            "name": endrulename,
            "conditions": [
                {
                    "address": sensoraddr + "/state/flag",
                    "operator": "eq",
                    "value": "true"
                },
                {
                    "address": sensoraddr + "/state/flag",
                    "operator": "ddx",
                    "value": offtimedelay
                }
            ],
            "actions": [
                {
                    "address": "/groups/${group:" + group + "}/action",
                    "method": "PUT",
                    "body": {
                        "on": False
                    }
                },
                {
                    "address": sensoraddr + "/state",
                    "method": "PUT",
                    "body": {
                        "flag": False
                    }
                }
            ]
        }

        if not groupid in self.__scenesToCreate:
            self.__scenesToCreate[groupid] = []
        self.__scenesToCreate[groupid] += [startscene, endscene]
        self.__rulesToCreate += [startrule, endrule]
        self.__schedulesToCreate += [schedule1, schedule2]
        self.__groupsToAdd.append(groupid)

    def __rulesForBoot(self):
        """ Create boot rule to turn off all lights after reboot """
        # TODO this doesn't yet work correctly
        self.__rulesToCreate.append({
            "name": "Boot",
            "conditions": [
                # When the bridge reboots, it doesn't know about light states. Ultimately, it will
                # learn some lights are on, so the any_on on group 0 will be set. We'll react on it.
                #{
                #    "address": "/groups/0/state/any_on",
                #    "operator": "dx"
                #},
                #{
                #    "address": "/groups/0/state/any_on",
                #    "operator": "eq",
                #    "value": "true"
                #},
                # When the bridge starts, all sensors (including external input) are initialized to 0.
                # So check for it here.
                {
                    "address": "/sensors/" + self.__extinput + "/state/status",
                    "operator": "eq",
                    "value": "0"
                }
            ],
            "actions": [
                # Turn off the light, if any light is on.
                {
                    "address": "/groups/0/action",
                    "method": "PUT",
                    "body": { "on": False }
                },
                # Set status to 1, so we won't react next time.
                {
                    "address": "/sensors/" + self.__extinput + "/state",
                    "method": "PUT",
                    "body": { "status": 1 }
                }
            ]
        })

    def configure(self, config, name):
        """ Configure the bridge. See README.md for config structure """

        # find resourcelink, if any
        if name in self.__resourcelinks_idx:
            self.__linkToDelete = self.__resourcelinks_idx[name]

        currentconfig = None
        try:
            # first collect rules and sensors to delete
            for v in config:
                currentconfig = v
                tp = v["type"]
                if tp == "switch":
                    self.__rulesForSwitch(v)
                elif tp == "external":
                    self.__rulesForExternal(v)
                elif tp == "state"  or tp == "contact":
                    self.__prepareSensor(v)
                elif tp == "motion":
                    self.__rulesForMotion(v)
                elif tp == "wakeup":
                    self.__rulesForWakeup(v)
                elif tp == "boot":
                    self.__rulesForBoot()
                else:
                    raise Exception("Unknown configuration type '" + tp + "'")
            self.commit(name)
        except:
            print("ERROR while processing configuration " + name)
            pprint.pprint(currentconfig)
            raise

    def commit(self, name):
        """ Commit changes prepared by configure """
        # delete out-of-date rules, schedules, sensors, scenes and links
        deleteRuleIDs = list(set(self.__rulesToDelete))
        print("Rules to delete:", deleteRuleIDs)
        for i in deleteRuleIDs:
            self.__deleteRule(i)
        
        deleteScheduleIDs = list(set(self.__schedulesToDelete))
        print("Schedules to delete:", deleteScheduleIDs)
        for i in deleteScheduleIDs:
            self.__deleteSchedule(i)
        
        deleteSensorIDs = list(set(self.__sensorsToDelete))
        print("Sensors to delete:", deleteSensorIDs)
        for i in deleteSensorIDs:
            self.__deleteSensor(i)

        # delete scenes
        for gid in self.__scenesToDelete.keys():
            for i in self.__scenesToDelete[gid]:
                sceneID = self.__deleteScene(gid, self.__scenesToDelete[gid][i])

        if self.__linkToDelete:
            print("Resource link to delete:", self.__linkToDelete)
            self.__deleteResourceLink(self.__linkToDelete)

        # collects all resources created here to present them as one resource link
        links = []
        currentData = None

        try:
            # create any sensors needed to represent switch states
            #print("Sensors to create:")
            #pprint.pprint(self.__sensorsToCreate)
            for i in self.__sensorsToCreate:
                currentData = i
                sensorID = self.__createSensor(i)
                links.append("/sensors/" + sensorID)

            # create scenes
            for gid in self.__scenesToCreate.keys():
                #print("Scenes to create for group " + gid + ":")
                #pprint.pprint(self.__scenesToCreate[gid])
                for i in self.__scenesToCreate[gid]:
                    currentData = i
                    sceneID = self.__createScene(gid, i)
                    links.append("/scenes/" + sceneID)

            #print("Schedules to create:")
            self.__updateReferences(self.__schedulesToCreate)
            #pprint.pprint(self.__schedulesToCreate)
            for i in self.__schedulesToCreate:
                currentData = i
                scheduleID = self.__createSchedule(i)
                links.append("/schedules/" + scheduleID)

            #print("Rules to create:")
            self.__updateReferences(self.__rulesToCreate)
            #pprint.pprint(self.__rulesToCreate)
            for i in self.__rulesToCreate:
                currentData = i
                ruleID = self.__createRule(i)
                links.append("/rules/" + ruleID)

            for i in self.__groupsToAdd:
                links.append("/groups/" + i)

            # create resource with links to all new rules and sensors
            resourceData = {
                "name": name,
                "description": name + " behavior",
                "type": "Link",
                "classid": 20101,
                "recycle": False,
                "links": links
            }
            currentData = resourceData
            tmp = requests.post(self.urlbase + "/resourcelinks", json=resourceData)
            if tmp.status_code != 200:
                raise Exception("Cannot create resource link " + name + ": " + tmp.text)
            result = json.loads(tmp.text)[0];
            if not "success" in result:
                raise Exception("Cannot create resource link " + name + ": " + tmp.text)
            print("Created resource link " + name + " with ID " + result["success"]["id"])

            # at the end, make sure the variables are cleaned, since we committed all changes
            self.__prepare()
        except:
            print("ERROR creating object")
            pprint.pprint(currentData)
            self.__prepare()
            raise

    def __printForeign(self, tp, whitelist):
        data = self.__all[tp]
        print("Foreign " + tp + ":")
        for key in data.keys():
            desc = data[key]
            owner = None
            if "owner" in desc:
                owner = desc["owner"][0:32]
            elif "command" in desc and "address" in desc["command"]:
                owner = desc["command"]["address"][5:37]
            else:
                raise Exception("Cannot find owner of " + desc["name"] + ", id=" + key + ", data=" + str(desc))
            if owner != self.apiKey[0:32] and not owner in whitelist:
                print(" -", key, "name=" + desc["name"] + ", owner=" + owner)
                continue
            if not desc["recycle"] and tp != "resourcelinks":
                print(" - NOT RECYCLING", key, "name=" + desc["name"] + ", owner=" + owner)

    def findForeignData(self, ignoreKeys):
        # print all rules, sensors, etc. which don't belong to us or other whitelisted app
        whitelist = set()
        for i in ignoreKeys:
            whitelist.add(i[0:32])
        self.__printForeign('rules', whitelist)
        self.__printForeign('schedules', whitelist)
        self.__printForeign('resourcelinks', whitelist)
        # check also for empty resource links
        linksToDelete = []
        for key in self.__resourcelinks.keys():
            desc = self.__resourcelinks[key]
            if len(desc["links"]) == 0:
                print(" - empty resource link " + key + " name=" + desc["name"] + "owner=" + desc["owner"])
                if (desc["owner"][0:32] == self.apiKey[0:32]):
                    print("   (own empty resource, deleting)")
                    linksToDelete.append(key)
        for linkID in linksToDelete:
            self.__deleteResourceLink(linkID)
        print("Own resourcelinks:")
        for key in self.__resourcelinks.keys():
            desc = self.__resourcelinks[key]
            if desc["owner"][0:32] == self.apiKey[0:32]:
                print(" - " + key + ": " + desc["name"])

    def listAll(self):
        # list all resorces
        print("Lights:")
        for i in self.__lights.keys():
            light = self.__lights[i]
            print("  - " + i + ": " + light["name"])

        print("Sensors:")
        for i in self.__sensors.keys():
            sensor = self.__sensors[i]
            print("  - " + i + ": " + sensor["name"] + " (" + sensor["type"] + ")")

        print("Rules:")
        for i in self.__rules.keys():
            rule = self.__rules[i]
            print("  - " + i + ": " + rule["name"])

    # TODO add boot time rule
    # TODO check all external inputs for non-overlapping