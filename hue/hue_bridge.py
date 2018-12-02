# coding=utf-8

'''
Created on 20 Nov 2018

@author: Ivan Schreter
'''
import requests
import json
import re
import pprint
from copy import deepcopy

VAR_PATTERN = re.compile("\\${([^}:]+):([^}]+)}")
SCENE_PATTERN = re.compile("^([^:]+):(.*)$")

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
        self.__scenes = self.__all["scenes"]
        self.__scenes_idx = {}
        for i in self.__scenes.keys():
            s = self.__scenes[i]
            n = s["name"]
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
            n = s["name"]
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
        tmp = requests.post(self.urlbase + "/sensors", json=sensorData)
        if tmp.status_code != 200:
            raise Exception("Cannot create sensor " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        sensorID = result["success"]["id"]
        self.__sensors_idx[name] = sensorID
        self.__sensors[sensorID] = sensorData
        print("Created sensor", sensorID, name)

    def __deleteRule(self, ruleID):
        name = self.__rules[ruleID]["name"]
        tmp = requests.delete(self.urlbase + "/rules/" + ruleID)
        if tmp.status_code != 200:
            raise Exception("Cannot delete rule " + ruleID + "/" + name + ": " + tmp.text)
        del self.__rules[ruleID]
        print("Deleted rule", ruleID, name)
        
    def __createRule(self, ruleData):
        name = ruleData["name"]
        tmp = requests.post(self.urlbase + "/rules", json=ruleData)
        if tmp.status_code != 200:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        result = json.loads(tmp.text)[0];
        if not "success" in result:
            raise Exception("Cannot create rule " + name + ": " + tmp.text)
        ruleID = result["success"]["id"]
        self.__rules[ruleID] = ruleData
        print("Created rule", ruleID, name)

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
                    "recycle": False,
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
                "recycle": False,
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
    
    def __redirectRule(self, binding, name, ref, conditions):
        value = binding["value"]
        return {
            "name": name + " " + ref + "->" + value,
            "status": "enabled",
            "recycle": False,
            "conditions": conditions,
            "actions": [
                {
                    "address": "/sensors/" + self.__extinput + "/state",
                    "method": "PUT",
                    "body": {
                        "status": int(value)
                    }
                }
            ]
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
        if "timeout" in config:
            # create second rule based on rule to turn off light and modify its dx condition to ddx with timeout
            """ NOTE: this doesn't work yet, since state after a timeout is different. Use schedules instead.
            timeout = "PT" + config["timeout"]
            conditions2 = deepcopy(conditions)
            founddx = False
            for cond in conditions2:
                if cond["operator"] == "dx":
                    cond["operator"] = "ddx"
                    cond["value"] = timeout
                    founddx = True
                    break
            if not founddx:
                raise Exception("Trying to add timeout for rule w/o dx operator: " + str(rule))
            rule2 = {
                "name": name + "/TO",
                "status": "enabled",
                "conditions": conditions2,
                "actions": [
                    {
                        "address": "/groups/" + groupID + "/action",
                        "method": "PUT",
                        "body": {
                            "on": False
                        }
                    }
                ]
            }
            return [rule, rule2]
            """
            return [rule]
        else:
            return [rule]
        
    def __sceneRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for switching to a scene """
        state = self.__parseCommon(binding, state)
        configs = binding["configs"]
        rules = []
        index = 0
        # if more than single config, we have a multistate switch, either time-based or multi-sstate or combined
        multistate = len(configs) > 1
        if multistate and not "state" in state and not "times" in binding:
            raise Exception("Missing state configuration for a multistate config w/o times for " + name + "/" + ref)
        secondaryState = state["stateUse"] == "secondary";
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
                        stateAction = []
                        if multistate and "state" in state:
                            # only trigger if state not yet set
                            stateCond += [
                                {
                                    "address": "/sensors/${sensor:" + state["state"] + "}/state/status",
                                    "operator": "gt" if secondaryState else "lt",
                                    "value": str(-1 if secondaryState else 1)
                                }
                            ]
                            stateAction += [
                                {
                                    "address": "/sensors/${sensor:" + state["state"] + "}/state",
                                    "method": "PUT",
                                    "body": {
                                        "status": -nextIndex if secondaryState else nextIndex
                                    }
                                }
                            ]
                        rules += self.__singleSceneRules(config, cname + "/T" + str(tidx), state, conditions + stateCond, actions + stateAction)
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
                    rules += self.__singleSceneRules(config, cname, state, conditions, actions)
            index = index + 1
        return rules
        
    def __lightRules(self, binding, name, ref, state, conditions, actions):
        """ Rules for switching a single light """
        state = self.__parseCommon(binding, state)
        lightID = self.findLight(binding["light"])
        action = binding["action"]
        rules = []
        if action == "on" or action == "off":
            rule = {
                "name": name,
                "status": "enabled",
                "recycle": False,
                "conditions": conditions,
                "actions": actions + [
                    {
                        "address": "/lights/" + lightID + "/action",
                        "method": "PUT",
                        "body": {
                            "on": True if action == "on" else False
                        }
                    }
                ]
            }
            rules.append(rule)
        elif action == "toggle":
            rule = {
                "name": name + " toggle ON",
                "status": "enabled",
                "recycle": False,
                "conditions": conditions + [
                    {
                        "address": "/lights/" + lightID + "/state/on",
                        "operator": "eq",
                        "value": "false"
                    }
                ],
                "actions": actions + [
                    {
                        "address": "/lights/" + lightID + "/state",
                        "method": "PUT",
                        "body": { "on": True }
                    }
                ]
            }
            rules.append(rule)
            rule = {
                "name": name + " toggle OFF",
                "status": "enabled",
                "recycle": False,
                "conditions": conditions + [
                    {
                        "address": "/lights/" + lightID + "/state/on",
                        "operator": "eq",
                        "value": "true"
                    }
                ],
                "actions": actions + [
                    {
                        "address": "/lights/" + lightID + "/state",
                        "method": "PUT",
                        "body": { "on": False }
                    }
                ]
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
        if tp == "redirect":
            # NOTE: explicitly ignore passed actions, since they reset external input to 1, when called for external
            rule = self.__redirectRule(binding, name, ref, conditions)
            return [rule]
        elif tp == "scene":
            return self.__sceneRules(binding, name, ref, state, conditions, actions)
        elif tp == "light":
            return self.__lightRules(binding, name, ref, state, conditions, actions)
        elif tp == "dim":
            return self.__dimRules(binding, name, ref, state, conditions, actions)
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
           - 0: the motion sensor is armed and will turn on the light
           - 1: the light is on, we are in timeout phase
           - 2: the light is in dimmed state
           - 3: the light is on and updates are blocked by door contact
        
        Following states and transitions are used:
            - 0: initial state, no motion, lights are off *or* motion not detected anymore, lights are on
                rule(1): motion detected in dark and lights off: turn on lights and switch to state 1
                This should be possible with a single rule just checking state of presence and dark,
                turning lights on and moving to state 1 when both of them detected.
                rule(2): motion detected and lights on switches to state 1
                rule(3): timer starts after entering state 0, after a timeout:
                    if lights are on and state is still 0
                    dim lights and enter state 2
            - 1: motion detected, lights are on
                rule(4): no motion detected in state 1:
                    switch to state 0 (lights still on; rule(2) switches back to state 1 upon motion)
                Here, we should not react on dx operator, but simple check for state and presence, since
                switch might switch to state 1, but that wouldn't trigger any timeout if noone comes into
                the room. When using just a plain check, we'd fall back to state 0 and start timeout,
                even if noone enters the room.
            - 2: light is dimmed:
                rule(5): timer starts after entering state 2, after a timeout:
                    if state is still 2, turn lights off and enter state 0 (off)
                rule(6): if motion is detected in state 2: restore lights and change state to 1
        If a door sensor is used:
            - 3: door contact closed
                when door contact goes to closed:
                    rule(7): transition from states 0-1 to 3, keeping light state
                    rule(8): transition from state 2 to 3, restore lights
                rule(9): check after a 16s timeout (motion sensor reports non-presence at the latesst after 15s):
                    if no motion is detected and state is still 3
                    turn lights off and switch to state 0
                when door contact goes to open,
                    rule(10): switch to state 1 if motion is currently detected
                    rule(11): switch to state 0 otherwise
                    
        If a switch is used to turn on lights, then the switch should in addition to setting light actions also:
            - transition to state 1 when turning lights on, unless already in state 3
            - transition to state 0 when turning lights off
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
        sceneName = name + " restore"
        if not sceneName in self.__scenes_idx[groupID]:
            raise Exception("Missing scene '" + sceneName + "'")
        sceneID = self.__scenes_idx[groupID][sceneName]
        
        rules = []
        conditions = []        
        actions = []
        onactions = None
        offactions = None
        for act in bindings.keys():
            binding = bindings[act]
            if act == "on":
                onactions = binding
            elif act == "off":
                offactions = binding
            else:
                raise Exception("Unsupported binding '" + act + "' for motion sensor")
        
        # handling for state 0
        
        # rule(1): motion detected in dark and lights off: turn on lights and switch to state 1
        if onactions:
            # only create if we have any on-action
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
                # NOTE: do not test for current state, react in any state (e.g., closed door in state 3 and lights off)
                #{
                #    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                #    "operator": "eq",
                #    "value": "0"
                #},
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
            rules += self.__createRulesForAction(onactions, name, "pres.on", state, conditions, actions)
        
        # rule(2): motion detected and lights on switches to state 1
        rules.append({
            "name": name + "/motion",
            "recycle": False,
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "true"
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "eq",
                    "value": "0"
                },
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "true"
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

        # rule(3): timer starts after entering state 0, after a timeout:
        #          if lights are on and state is still 0
        #          dim lights and enter state 2
        rules.append({
            "name": name + "/dim",
            "recycle": False,
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
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
            ],
            "actions": [
                {
                    "address": "/scenes/" + sceneID,
                    "method": "PUT",
                    "body": {
                        "storelightstate": True
                    }
                },
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "bri_inc": -128
                    }
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 2
                    }
                }
            ]
        })

        # handling for state 1: motion detected, lights are on
        
        # rule(4): no motion detected in state 1:
        #            switch to state 0 (lights still on; rule(2) switches back to state 1 upon motion)
        rules.append({
            "name": name + "/pres.off",
            "recycle": False,
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
        
        # rule(5): timer starts after entering state 2, after a timeout:
        #            if state is still 2, turn lights off and enter state 0 (off)
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
                    "status": 0
                }
            }
        ]
        if offactions:
            # explicit off action specified
            rules += self.__createRulesForAction(offactions, name, "off", state, conditions, actions)
        else:
            # no off action, add default one (group off)
            rules.append({
                "name": name + "/off",
                "recycle": False,
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

        #  rule(6): if motion is detected in state 2: restore lights and change state to 1
        rules += [{
            "name": name + "/recover",
            "conditions": [
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
            ],
            "actions": [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "scene": sceneID
                    }
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 1
                    }
                }
            ]
        }]        
        
        # handling for state 3: door contact closed
        
        if "contact" in desc:
            # Add rules to handle door contact. When the door is closed and motion has been
            # detected after the door is closed, then don't react until door is open
            # again. If no motion has been detected after door is closed, then turn off light.
            
            # The sensor sends a no-presence signal after 10 seconds of no-presence detection.
            # So check after 11 seconds after closing doors whether there is presence or not.
            
            contactName = desc["contact"]

            # when door contact goes to closed:
            rules += [
                # rule(7): transition from states 0-1 to 3, keeping light state
                {
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
                },
                # rule(8): transition from state 2 to 3, restore lights
                {
                    "name": name + "/cl.rest",
                    "actions" : [
                        {
                            "address": "/groups/" + groupID + "/action",
                            "method": "PUT",
                            "body": {
                                "scene": sceneID
                            }
                        },
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
                }
            ]

            # rule(9): check after a 16s timeout:
            #    if no motion is detected and state is still 3
            #    turn lights off and switch to state 0
            actions = [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 0
                    }
                }
            ]
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
            if offactions:
                # explicit off action specified
                rules += self.__createRulesForAction(offactions, name, "clo.off", state, conditions, actions)
            else:
                # no off action, add default one (group off)
                rules.append({
                    "name": name + "/clo.off",
                    "recycle": False,
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

            # when door contact goes to open
            rules += [
                # rule(10): switch to state 0, when door open and previously closed
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
                            "operator": "eq",
                            "value": "3"
                        },
                        {
                            "address": "/sensors/${sensor:" + contactName + "}/state/status",
                            "operator": "eq",
                            "value": "0"
                        }
                        # NOTE: do not only react on change to contact sensor, also react when contact is off and state is not 3
                        #{
                        #    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                        #    "operator": "dx",
                        #}
                    ]
                }
            ]

        return rules
                    
    def __rulesForMotionOld(self, sensorID, desc):
        """ Old-style rules for motion sensor, just for reference """
        state = self.__parseCommon(desc)
        groupID = self.__groups_idx[state["group"]]
        bindings = desc["bindings"]
        name = desc["name"]
        stateSensorName = desc["state"]
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
        sceneName = name + " restore"
        if not sceneName in self.__scenes_idx[groupID]:
            raise Exception("Missing scene '" + sceneName + "'")
        sceneID = self.__scenes_idx[groupID][sceneName]
        
        rules = []
        conditions = []        
        actions = []
        for act in bindings.keys():
            binding = bindings[act]
            if act == "on":
                actions = [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 1
                        }
                    }
                ]
                conditions = [
                    {
                        "address": "/sensors/" + sensorID + "/state/presence",
                        "operator": "eq",
                        "value": "true"
                    },
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "lt",
                        "value": "1"
                    },
                    {
                        "address": "/sensors/" + lightSensorID + "/state/dark",
                        "operator": "eq",
                        "value": "true"
                    },
                    {
                        "address": "/sensors/" + sensorID + "/state/presence",
                        "operator": "dx"
                    }
                ]
                rules += self.__createRulesForAction(binding, name, "on.pres", state, conditions, actions)
                conditions = [
                    {
                        "address": "/sensors/" + sensorID + "/state/presence",
                        "operator": "eq",
                        "value": "true"
                    },
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "lt",
                        "value": "1"
                    },
                    {
                        "address": "/sensors/" + lightSensorID + "/state/dark",
                        "operator": "eq",
                        "value": "true"
                    },
                    {
                        "address": "/sensors/" + lightSensorID + "/state/dark",
                        "operator": "dx"
                    }
                ]
                rules += self.__createRulesForAction(binding, name, "on.dark", state, conditions, actions)
            elif act == "off":
                actions = [
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                        "method": "PUT",
                        "body": {
                            "status": 0
                        }
                    }
                ]
                conditions = [
                    {
                        "address": "/sensors/" + sensorID + "/state/presence",
                        "operator": "eq",
                        "value": "false"
                    },
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "ddx",
                        "value": "PT00:00:30"
                    },
                    {
                        "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                        "operator": "eq",
                        "value": "2"
                    }
                ]
                rules += self.__createRulesForAction(binding, name, "off", state, conditions, actions)
        
        # add re-arming, when the light is off and sensor shows no presence
        rule = {
            "name": name + "/arm",
            "recycle": False,
            "conditions": [
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
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
        }
        rules.append(rule)

        # add dimming after timeout and recovery on presence
        rules += [{
            "name": name + "/dim",
            "recycle": False,
            "conditions": [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "ddx",
                    "value": "PT" + desc["timeout"]
                },
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "true"
                },
                # dim if the light is on, either through sensor or through light on
                # this works only after presence, but doesn't timeout on switch with no presence
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                    "operator": "lt",
                    "value": "2"
                }
            ],
            "actions": [
                {
                    "address": "/scenes/" + sceneID,
                    "method": "PUT",
                    "body": {
                        "storelightstate": True
                    }
                },
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "bri_inc": -128
                    }
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 2
                    }
                }
            ]
        },
        {
            "name": name + "/recover",
            "conditions": [
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
            ],
            "actions": [
                {
                    "address": "/groups/" + groupID + "/action",
                    "method": "PUT",
                    "body": {
                        "scene": sceneID
                    }
                },
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 1
                    }
                }
            ]
        }]
        
        if "contact" in desc:
            # Add rules to handle door contact. When the door is closed and motion has been
            # detected after the door is closed, then don't react until door is open
            # again. If no motion has been detected after door is closed, then turn off light.
            
            # The sensor sends a no-presence signal after 10 seconds of no-presence detection.
            # So check after 11 seconds after closing doors whether there is presence or not.
            contactName = desc["contact"]
            # first rule fires if there is someone behind closed door
            rules.append(
                {
                    "name": name + "/clo.on",
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
                            "address": "/sensors/" + sensorID + "/state/presence",
                            "operator": "eq",
                            "value": "true"
                        },
                        # fire if any light is on and we are not yet in dimming phase
                        {
                            "address": "/groups/" + groupID + "/state/any_on",
                            "operator": "eq",
                            "value": "true"
                        },
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
                        {
                            "address": "/sensors/${sensor:" + contactName + "}/state/status",
                            "operator": "ddx",
                            "value": "PT00:00:12"
                        }
                    ]
                }
            )
            # second rule fires if there is noone behind closed door
            actions = [
                {
                    "address": "/sensors/${sensor:" + stateSensorName + "}/state",
                    "method": "PUT",
                    "body": {
                        "status": 0
                    }
                }
            ]
            conditions = [
                {
                    "address": "/sensors/" + sensorID + "/state/presence",
                    "operator": "eq",
                    "value": "false"
                },
                # fire if any light is on and we are not yet in dimming phase
                {
                    "address": "/groups/" + groupID + "/state/any_on",
                    "operator": "eq",
                    "value": "true"
                },
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
                {
                    "address": "/sensors/${sensor:" + contactName + "}/state/status",
                    "operator": "ddx",
                    "value": "PT00:00:11"
                }
            ]
            rules += self.__createRulesForAction(binding, name, "clo.off", state, conditions, actions)
            # opening the door will allow rearming the timeout when the person leaves the room
            # TODO this relies on motion detection during leaving the room, which should be given.
            # Can we do better? Probably yes by delegating presence sensor change to state sensor
            # change, then we can set state sensor here and ddx on state sensor instead of motion
            # sensor.
            rules.append(
                {
                    "name": name + "/open",
                    "conditions": [
                        {
                            "address": "/sensors/${sensor:" + contactName + "}/state/status",
                            "operator": "eq",
                            "value": "0"
                        },
                        {
                            "address": "/sensors/${sensor:" + stateSensorName + "}/state/status",
                            "operator": "eq",
                            "value": "3"
                        },
                        {
                            "address": "/sensors/${sensor:" + contactName + "}/state/status",
                            "operator": "dx"
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
                }
            )

        return rules
                    
    def __createScene(self, groupID, sceneName):
        body = {
            "name": sceneName,
            "lights": self.__groups[groupID]["lights"], 
            #"group": groupID,
            "recycle": False
        }
        r = requests.post(self.urlbase + "/scenes", json=body)
        if r.status_code != 200:
            raise Exception("Cannot create scene '" + sceneName + "', text=" + r.text)
        r.encoding = 'utf-8'
        res = json.loads(r.text)
        if not "success" in res[0]:
            raise Exception("Cannot create scene '" + sceneName + "', error: " + r.text)
        self.__scenes_idx[groupID][sceneName] = res[0]["success"]["id"]
        
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
            "uniqueid": name,
            "recycle": False
        }
        newSensors.append(sensorData)
        newRules += self.__ruleForSensorReset(v)
        if v["type"] == "contact":
            newRules += self.__rulesForContact(v)
        return [newSensors, newRules, deleteSensorIDs, deleteRuleIDs]

    def configure(self, config):
        """ Configure the bridge. See README.md for config structure """

        # first collect rules and sensors to delete
        deleteSensorIDs = []
        deleteRuleIDs = []
        newSensors = []
        newRules = []
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
                sceneName = v["name"] + " restore"
                groupID = self.__groups_idx[v["group"]]
                if not sceneName in self.__scenes_idx[groupID]:
                    # create new scene for the group
                    self.__createScene(groupID, sceneName)
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
        
        # TODO delete resource

        # create any sensors needed to represent switch states
        #print("Sensors to create:")
        #pprint.pprint(newSensors)
        for i in newSensors:
            self.__createSensor(i)

        # update references in rules
        self.__updateReferences(newRules)
        
        # create rules for sensors and external input
        #print("Rules to create:")
        #pprint.pprint(newRules)
        for i in newRules:
            self.__createRule(i)

        # TODO create resource with links to all new rules and sensors
