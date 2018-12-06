'''
Created on 20 Nov 2018

@author: Ivan Schreter
'''
import requests
import json
import re
from copy import deepcopy

VAR_PATTERN = re.compile("\\${([^}:]+):([^}]+)}")
SCENE_PATTERN = re.compile("^([^:]+):(.*)$")
OFF_BINDING = { "type": "scene", "configs": [ {"scene": "off"} ] }

BUTTON_MAP = {
    # mapping for dimmer
    "on": "1000",
    "on-hold": "1001",
    "on-release": "1003",
    "brighter": "2000",
    "brighter-hold": "2001",
    "brighter-release": "2003",
    "darker": "3000",
    "darker-hold": "3001",
    "darker-release": "3003",
    "off": "4000",
    "off-hold": "4001",
    "off-release": "4003",
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
    "top-both": "99",
    "tlr": "99",
    "bottom-both": "101",
    "blr": "101"
    }

class HueBridge():
    """
    Class for configuring various sensor rules in Philips Hue bridge using a simple JSON description

    See README.md for description of the configuration.
    """

    # Rules to append to bindings for a dimmer for dimming up/down. Requires group set in descriptor.
    DIMMER_RULES = {
        "brighter": { "type": "dim", "value": 30 },
        "brighter-hold": { "type": "dim", "value": 56 },
        "brighter-release": { "type": "dim", "value": 0, "tt": 0 },
        "darker": { "type": "dim", "value": -30 },
        "darker-hold": { "type": "dim", "value": -56 },
        "darker-release": { "type": "dim", "value": 0, "tt": 0 }
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
                print("WARNING: Duplicate scene name '" + n + "' for group " + g + " ('" + self.__groups[g]["name"] + "')")
            else:
                self.__scenes_idx[g][n] = i
        self.__rules = self.__all["rules"]
        
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
    def __make_index(array, tp, ignore = []):
        index = {}
        for i in array.keys():
            s = array[i]
            n = s["name"].strip()
            if not n in ignore:
                if n in index:
                    raise Exception(u"Duplicate name '" + n + "' in " + tp + ", indices " + index[n] + " and " + i)
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
            raise Exception("Cannot create sensor " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
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
        name = fullname[0:32]
        if name != fullname:
            print("WARNING: Shortening rule name '" + fullname + "' to '" + name + "'")
        ruleData["name"] = name
        ruleData["recycle"] = True
        tmp = requests.post(self.urlbase + "/rules", json=ruleData)
        if tmp.status_code != 200:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        ruleID = result["success"]["id"]
        ruleData["owner"] = self.apiKey
        self.__rules[ruleID] = ruleData
        print("Created rule", ruleID, name)
        return ruleID

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
            usecount = 1
            if "uses" in v:
                usecount = v["uses"]
                if usecount != 1 and usecount != 2:
                    raise Exception("Use count must be 1 or 2 for " + name)
            rules = []
            for i in range(0, usecount):
                ruleData = {
                    "name": name + " timeout " + str(i + 1),
                    "status": "enabled",
                    "conditions": [
                        {
                            "address": "/sensors/${sensor:" + name + "}/state/lastupdated",
                            "operator": "ddx",
                            "value": "PT" + timeout
                        },
                        {
                            "address": "/sensors/${sensor:" + name + "}/state/status",
                            "operator": "lt" if i == 1 else "gt",
                            "value": "0"
                        }
                    ],
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
                rules.append(ruleData)
            return rules
        else:
            return []

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
        return rules

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
        return {
            "name": name + "/" + ref + "=" + value,
            "status": "enabled",
            "conditions": conditions,
            "actions": actions + resetActions
        }
        
    def __singleSceneRules(self, config, name, state, conditions, actions):
        """ Rules for a single config """            
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
        rule = {
            "name": name,
            "status": "enabled",
            "conditions": conditions,
            "actions": actions + sceneActions
        }
        return [rule]
        
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
        rules = []
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
                    rules += self.__singleSceneRules(config, cname, state, stateCond + conditions, stateAction + actions)
                
            if "times" in binding:
                # multiple time-based rules to turn on scenes, get the one for this index
                times = binding["times"]
                tidx = 0
                for timerange in times:
                    if times[timerange] == index:
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
                        rules += self.__singleSceneRules(config, cname + "/T" + str(tidx), state, conditions + stateCond, stateAction + actions)
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
                    rules += self.__singleSceneRules(config, cname + "/in", state, conditions + stateCond, actions + stateAction)
                else:
                    # single config, no additional conditions
                    rules += self.__singleSceneRules(config, cname, state, conditions, resetstateactions + actions)

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
                    "name": name + "/TO" + str(index),
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
                rules.append(rule)

            index = index + 1
        return rules
        
    def __lightRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for switching a single light """
        state = self.__parseCommon(binding, state)
        lightID = self.findLight(binding["light"])
        action = binding["action"]
        rules = []
        if action == "on" or action == "off":
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/action",
                    "method": "PUT",
                    "body": {
                        "on": True if action == "on" else False
                    }
                }
            ]

            rule = {
                "name": name,
                "status": "enabled",
                "conditions": conditions,
                "actions": actions + lightActions
            }
            rules.append(rule)
        elif action == "toggle":
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/state",
                    "method": "PUT",
                    "body": { "on": True }
                }
            ]
            rule = {
                "name": name + " toggle ON",
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
            rules.append(rule)
            lightActions = [
                {
                    "address": "/lights/" + lightID + "/state",
                    "method": "PUT",
                    "body": { "on": False }
                }
            ]
            rule = {
                "name": name + " toggle OFF",
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
            rules.append(rule)
        else:
            raise Exception("Invalid action '" + action + "', expected on/off/toggle")
        
        return rules

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
        return [rule]

    def __createRulesForAction(self, binding, name, ref, state, conditions = [], actions = []):
        state = self.__parseCommon(binding, state)
        tp = binding["type"]
        resetstateactions = []
        if "state" in state:
            resetstateactions = [
                {
                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                    "method": "PUT",
                    "body": { "status": 0 }
                }
            ]
        if tp == "redirect":
            # NOTE: explicitly ignore passed actions, since they reset external input to 1, when called for external
            rule = self.__redirectRule(binding, name, ref, state, conditions, resetstateactions)
            return [rule]
        elif tp == "scene":
            return self.__sceneRules(binding, name, ref, state, conditions, actions)
        elif tp == "off":
            return self.__sceneRules(OFF_BINDING, name, ref, state, conditions, actions)
        elif tp == "light":
            return self.__lightRules(binding, name, ref, state, conditions, resetstateactions + actions)
        elif tp == "dim":
            return self.__dimRules(binding, name, ref, state, conditions, resetstateactions + actions)
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
        rules = []
        for button in bindings.keys():
            binding = bindings[button]
            conditions = [
                {
                    "address": "/sensors/${sensor:" + switchName + "}/state/buttonevent",
                    "operator": "eq",
                    "value": HueBridge.__mapButton(button)
                },
                {
                    "address": "/sensors/${sensor:" + switchName + "}/state/lastupdated",
                    "operator": "dx"
                }
            ]
            rules += self.__createRulesForAction(binding, switchName, button, state, conditions, [])
        return rules
        
    def __rulesForExternal(self, desc):
        """ Create rules for external input """
        state = self.__parseCommon(desc)
        bindings = desc["bindings"]
        name = desc["name"]
        rules = []
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
            rules += self.__createRulesForAction(binding, name, extID, state, conditions, actions)
        return rules
                    
    def __rulesForMotion(self, sensorID, desc):
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
            - 0: initial state, no motion, lights are off *or* motion not detected anymore, lights are on
                rule(1-3): motion detected in dark and lights off: turn on lights and switch to state 1
                    This should be possible with a single rule just checking state of presence and dark,
                    turning lights on and moving to state 1 when both of them detected. However, it doesn't
                    work correctly, so currently we have 3 rules with dx on presence, dark and state change.
                rule(4): motion detected and lights on switches to state 1
                rule(5): timer starts after entering state 0, after a timeout:
                    if lights are on and state is still 0
                    dim lights and enter state 2
            - 1: motion detected, lights are on
                rule(6): no motion detected in state 1:
                    switch to state 0 (if lights still on, rule(2) switches back to state 1 upon motion)
                Here, we should not react on dx operator, but simple check for state and presence, since
                switch might switch to state 1, but that wouldn't trigger any timeout if noone comes into
                the room. When using just a plain check, we'd fall back to state 0 and start timeout,
                even if noone enters the room.
            - 2: light is dimmed:
                rule(7): timer starts after entering state 2, after a timeout:
                    if state is still 2, turn lights off and enter state -1 (off by sensor)
                rule(8): if motion is detected in state 2: recover light state and change state to 1

        Handling of turning on/off via switch or app:
            rule(9): after manually switched on, change state to 1 (which will transition to 0 upon no motion)
            rule(10): after manually switched off in state 0-2, change state to -2
            rule(11): after off timeout, change state -2->-1 to allow sensor to react

        If a door sensor is used:
            when door contact goes to closed:
                rule(12): transition from states <2 to 3, lights on, keeping light state
                rule(13): transition from state 2 to 3, recover light state
            when door contact is closed (state 3):
                rule(14): check after a 16s timeout (motion sensor reports non-presence at the latesst after 15s):
                    if no motion is detected and state is still 3 turn lights off and keep state 3
                rule(15): motion detected and lights off, door closed previously with lights on: turn on lights
            when door contact goes to open:
                rule(16): switch to state 0, independent of motion (rule(4) will switch to state 1)

        Motion sensor supports following bindings:
            - "on" - turn on the lights
            - "off" - turn off the lights (default: all lights in the group off)
            - "dim" - what to do on timeout (default: dim all lights in the group by 50%)
            - "recover" - what to do when motion detected in dimmed state (default: recover scene before dimming)
        """

        state = self.__parseCommon(desc)
        groupID = self.__groups_idx[state["group"]]
        bindings = desc["bindings"]
        name = desc["name"]
        stateSensorName = name + " state"
        if not "group" in state:
            raise Exception("No group set for motion sensor '" + name + "'")
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
        
        rules = []
        onactions = None
        offactions = None
        dimactions = None
        recoveractions = None
        for act in bindings.keys():
            binding = bindings[act]
            if act == "on":
                onactions = binding
            elif act == "off":
                offactions = binding
            elif act == "dim":
                dimactions = binding
            elif act == "recover":
                recoveractions = binding
            else:
                raise Exception("Unsupported binding '" + act + "' for motion sensor")
        if isinstance(recoveractions, str):
            if recoveractions == "on":
                recoveractions = onactions
            else:
                raise Exception("Unsupported recover action redirect '" + recoveractions + "' for motion sensor")

        sceneID = None
        if not recoveractions:
            # only use scene if no recover action
            sceneName = name + " recover"
            if not sceneName in self.__scenes_idx[groupID]:
                raise Exception("Missing scene '" + sceneName + "'")
            sceneID = self.__scenes_idx[groupID][sceneName]

        # handling for state 0
        
        # rule(1-3): motion detected in dark and lights off: turn on lights and switch to state 1
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
            # NOTE: react in any state except blocked by switch (e.g., closed door in state 3 and lights off)
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "gt",
                "value": "-2"
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "lt",
                "value": "3"
            },
            {
                "address": "/groups/" + groupID + "/state/any_on",
                "operator": "eq",
                "value": "false"
            }
        ]
        actions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": 1
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
        for i in [
            ["pres.on", {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "dx"
            }],
            ["dark.on", {
                "address": "/sensors/" + lightSensorID + "/state/dark",
                "operator": "dx"
            }],
            ["stat.on", {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "dx",
            }]
        ]:
            cname = i[0]
            condition = i[1]
            if onactions:
                rules += self.__createRulesForAction(onactions, name, cname, state, conditions + [condition], actions)
            else:
                rules.append({
                    "name": name + "/" + cname,
                    "conditions": conditions + [condition],
                    "actions": actions
                })

        # rule(4): motion detected and lights on switches to state 1
        rules.append({
            "name": name + "/motion",
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "true"
                },
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
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "true"
                }
                # NOTE: no dx/ddx operator here, it has to switch if conditions are met
                # (e.g., switch turned on or door goes to open)
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

        # rule(5): timer starts after entering state 0, after a timeout:
        #          if lights are on and state is still 0
        #          dim lights and enter state 2
        conditions = [
            {
                "address": "/sensors/" + sensorID + "/state/presence",
                "operator": "eq",
                "value": "false"
            },
            # ddx on last update of state sensor instead of presence sensor to turn off
            # also after switching light on w/o movement
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "ddx",
                "value": "PT" + desc["timeout"]
            },
            {
                "address": "/groups/" + groupID + "/state/any_on",
                "operator": "eq",
                "value": "true"
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "eq",
                "value": "0"
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
        if not recoveractions:
            # we need to store light state, so we can recover it on recover action
            actions.append({
                "address": "/scenes/" + sceneID,
                "method": "PUT",
                "body": {
                    "storelightstate": True
                }
            })
        if dimactions:
            # create copy of the state w/o "state" key, since we don't want to modify switch state here
            statecopy = deepcopy(state)
            statecopy.pop("state", None)
            rules += self.__createRulesForAction(dimactions, name, "dim", statecopy, conditions, actions)
        else:
            actions.append({
                "address": "/groups/" + groupID + "/action",
                "method": "PUT",
                "body": {
                    "bri_inc": -128
                }
            })
            rules.append({
                "name": name + "/dim",
                "conditions": conditions,
                "actions": actions
            })

        # handling for state 1: motion detected, lights are on
        
        # rule(6): no motion detected in state 1:
        #            switch to state 0 (if lights still on, rule(2) switches back to state 1 upon motion)
        rules.append({
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
                    "value": "1"
                }
            ],
            "actions": [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 0
                    }
                }
            ]
        })
                
        # hanlding for state 2: light is dimmed
        
        # rule(7): timer starts after entering state 2, after a timeout:
        #            if state is still 2, turn lights off and enter state -1 (off by sensor)
        dimtime = "PT00:00:20"
        if "dimtime" in desc:
            dimtime = "PT" + desc["dimtime"]
        conditions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "ddx",
                "value": dimtime
            },
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                "operator": "eq",
                "value": "2"
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
            rules += self.__createRulesForAction(offactions, name, "off", state, conditions, actions)
        else:
            # no off action, add default one (group off)
            rules.append({
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

        #  rule(8): if motion is detected in state 2: recover light state and change state to 1
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
                "value": "2"
            }
        ]
        actions = [
            {
                "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                "method": "PUT",
                "body": {
                    "status": 1
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
            rules += self.__createRulesForAction(recoveractions, name, "recover", state, conditions, actions)
        else:
            rules.append({
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

        # rule(9): after manually switched on, change state to 1 (which will transition to 0 upon no motion)
        rules.append(
            {
                "name": name + "/switch.on",
                "actions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 1
                        }
                    }
                ],
                "conditions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "lt",
                        "value": "1"
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
                ]
            }
        )
        
        # rule(10): after manually switched off in state 0-2, change state to -2
        rules.append(
            {
                "name": name + "/switch.off",
                "actions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": -2    # this prevents turning on by sensor
                        }
                    }
                ],
                "conditions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "lt",
                        "value": "3"
                    },
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

        # Handling for state -2 for timeouts on switch on/off
        # rule(11): after off timeout, change state -2->-1
        offtimeout = "PT00:00:30"
        if "offtimeout" in desc:
            offtimeout = "PT" + desc["offtimeout"]
        rules.append(
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
        

        # handling for state 3: door contact closed
        
        if "contact" in desc:
            # Add rules to handle door contact. When the door is closed and motion has been
            # detected after the door is closed, then don't react until door is open
            # again. If no motion has been detected after door is closed, then turn off light.
            
            # The sensor sends a no-presence signal after 10 seconds of no-presence detection.
            # So check after 11 seconds after closing doors whether there is presence or not.
            
            contactName = desc["contact"]

            # when door contact goes to closed:

            # rule(12): transition from states <2 to 3, lights on, keeping light state
            rules.append({
                "name": name + "/closed",
                "actions" : [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 3
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
                        "address": "/sensors/${sensor:" + contactName + "}/state/status",
                        "operator": "eq",
                        "value": "1"
                    },
                    # NOTE: do not only react on change to contact sensor, also react when contact is on and state is not 3
                    #{
                    #    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    #    "operator": "dx",
                    #}
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "eq",
                        "value": "true"
                    }
                ]
            })

            # rule(13): transition from state 2 to 3, recover light state
            actions = [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 3
                    }
                }
            ]
            conditions = [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "2"
                },
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                }
                # NOTE: do not only react on change to contact sensor, also react when contact is on and state is not 3
                #{
                #    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                #    "operator": "dx",
                #}
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
                rules += self.__createRulesForAction(recoveractions, name, "clo.rec", state, conditions, actions)
            else:
                rules.append({
                    "name": name + "/clo.rec",
                    "conditions": conditions,
                    "actions": [{
                        "address": "/groups/" + groupID + "/action",
                        "method": "PUT",
                        "body": {
                            "scene": sceneID
                        }
                    }] + actions
                })

            # rule(14): check after a 16s timeout:
            #    if no motion is detected and state is still 3 turn lights off and keep state 3
            actions = []
            conditions = [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "3"
                },
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "eq",
                    "value": "1"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "ddx",
                    "value": "PT00:00:16"
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
            if offactions:
                # explicit off action specified
                rules += self.__createRulesForAction(offactions, name, "clo.off", state, conditions, actions)
            else:
                # no off action, add default one (group off)
                rules.append({
                    "name": name + "/clo.off",
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

                # rule(15): motion detected and lights off, door closed previously with light on: turn on lights
                conditions = [
                    {
                        "address": "/sensors/" + sensorID + "/state/presence",
                        "operator": "eq",
                        "value": "true"
                    },
                    #{
                    #    "address": "/sensors/" + sensorID + "/state/presence",
                    #    "operator": "dx",
                    #},
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "eq",
                        "value": "3"
                    },
                    {
                        "address": "/groups/" + groupID + "/state/any_on",
                        "operator": "eq",
                        "value": "false"
                    }
                ]
                actions = []
                if "state" in state:
                    # reset associated switch sensor state before turning on lights (typically turned on via redirect)
                    actions.append(
                        {
                            "address": "/sensors/${sensor:" + state["state"] + "}/state",
                            "method": "PUT",
                            "body": { "status": 0 }
                        }
                    )
                if onactions:
                    rules += self.__createRulesForAction(onactions, name, "clo.on", state, conditions, actions)
                else:
                    rules.append({
                        "name": name + "/clo.on",
                        "conditions": conditions,
                        "actions": actions
                    })

            # when door contact goes to open
            rules += [
                # rule(16): switch to state 0, independent of motion (rule(4) will switch to state 1)
                {
                    "name": name + "/open",
                    "actions" : [
                        {
                            "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                            "method": "PUT",
                            "body": {
                                "status": 0
                            }
                        }
                    ],
                    "conditions" : [
                        {
                            "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                            "operator": "gt",
                            "value": "2"
                        },
                        {
                            "address": "/sensors/${sensor:" + contactName + "}/state/status",
                            "operator": "eq",
                            "value": "0"
                        }
                    ]
                }
            ]

        return rules
                    
    def __createScene(self, groupID, sceneName):
        body = {
            "name": sceneName,
            "lights": self.__groups[groupID]["lights"], 
            #"group": groupID,
            "recycle": True
        }
        r = requests.post(self.urlbase + "/scenes", json=body)
        if r.status_code != 200:
            raise Exception("Cannot create scene '" + sceneName + "', text=" + r.text)
        r.encoding = 'utf-8'
        res = json.loads(r.text)
        if not "success" in res[0]:
            raise Exception("Cannot create scene '" + sceneName + "', error: " + r.text)
        sceneID = res[0]["success"]["id"]
        body["owner"] = self.apiKey
        self.__scenes[sceneID] = body
        self.__scenes_idx[groupID][sceneName] = sceneID
        print("Created scene", sceneID, sceneName, "for group", groupID)
        return sceneID
        
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

    def __prepareSensor(self, v):
        name = v["name"]
        s = self.findSensor(name)
        deleteSensorIDs = []
        deleteRuleIDs = []
        newSensors = []
        newRules = []
        if s:
            if self.__sensors[s]["type"] != "CLIPGenericStatus":
                raise Exception("Sensor '" + name + "' is not a generic status sensor")
            deleteSensorIDs.append(s)
            deleteRuleIDs += self.findRulesForSensorID(s)
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
        newSensors.append(sensorData)
        newRules += self.__ruleForSensorReset(v)
        if v["type"] == "contact":
            newRules += self.__rulesForContact(v)
        return [newSensors, newRules, deleteSensorIDs, deleteRuleIDs]

    def configure(self, config, name):
        """ Configure the bridge. See README.md for config structure """

        # find resourcelink, if any
        linkID = None
        if name in self.__resourcelinks_idx:
            linkID = self.__resourcelinks_idx[name]

        # first collect rules and sensors to delete
        deleteSensorIDs = []
        deleteRuleIDs = []
        newSensors = []
        newRules = []
        links = []
        for v in config:
            tp = v["type"]
            if tp == "switch":
                switchID = self.findSensor(v["name"])
                if not switchID:
                    raise Exception("Switch '" + v["name"] + "' not found")
                deleteRuleIDs += self.findRulesForSensorID(switchID)
                newRules += self.__rulesForSwitch(v)
            elif tp == "external":
                deleteRuleIDs += self.findRulesForExternalID(v["bindings"].keys())
                newRules += self.__rulesForExternal(v)
            elif tp == "state"  or tp == "contact":
                res = self.__prepareSensor(v)
                newSensors += res[0]
                newRules += res[1]
                deleteSensorIDs += res[2]
                deleteRuleIDs += res[3]
            elif tp == "motion":
                sensorID = self.findSensor(v["name"])
                res = self.__prepareSensor({
                    "type": "state",
                    "name": v["name"] + " state"
                })
                newSensors += res[0]
                newRules += res[1]
                deleteSensorIDs += res[2]
                deleteRuleIDs += res[3]
                if not sensorID:
                    raise Exception("Sensor '" + v["name"] + "' not found")
                if self.__sensors[sensorID]["type"] != "ZLLPresence":
                    raise Exception("Sensor '" + v["name"] + "' is not a presence sensor")
                deleteRuleIDs += self.findRulesForSensorID(sensorID)
                sceneName = v["name"] + " recover"
                groupID = self.__groups_idx[v["group"]]
                if not sceneName in self.__scenes_idx[groupID] and not "recover" in v["bindings"]:
                    # create new scene for the group to store light state to recover
                    sceneID = self.__createScene(groupID, sceneName)
                    links.append("/scenes/" + sceneID)
                newRules += self.__rulesForMotion(sensorID, v)
            else:
                raise Exception("Unknown configuration type '" + tp + "'")

        # delete out-of-date rules and sensors
        deleteRuleIDs = list(set(deleteRuleIDs))
        print("Rules to delete:", deleteRuleIDs)
        for i in deleteRuleIDs:
            self.__deleteRule(i)
        
        deleteSensorIDs = list(set(deleteSensorIDs))
        print("Sensors to delete:", deleteSensorIDs)
        for i in deleteSensorIDs:
            self.__deleteSensor(i)
        
        if linkID:
            print("Resource link to delete:", linkID)
            self.__deleteResourceLink(linkID)

        # create any sensors needed to represent switch states
        #print("Sensors to create:")
        #pprint.pprint(newSensors)
        for i in newSensors:
            sensorID = self.__createSensor(i)
            links.append("/sensors/" + sensorID)

        # update references in rules
        self.__updateReferences(newRules)
        
        # create rules for sensors and external input
        #print("Rules to create:")
        #pprint.pprint(newRules)
        for i in newRules:
            ruleID = self.__createRule(i)
            links.append("/rules/" + ruleID)

        # create resource with links to all new rules and sensors
        resourceData = {
            "name": name,
            "description": "Rules generated for: " + name,
            "type": "Link",
            "classid": 4711,
            "recycle": False,
            "links": links
        }
        tmp = requests.post(self.urlbase + "/resourcelinks", json=resourceData)
        if tmp.status_code != 200:
            raise Exception("Cannot create resource link " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create resource link " + name + ": " + tmp.text)
        print("Created resource link " + name + " with ID " + result["success"]["id"])

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

    # TODO add boot time rule
    # TODO check all external inputs for non-overlapping