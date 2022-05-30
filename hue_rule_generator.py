'''
Created on 20 Nov 2018

@author: Ivan Schreter

The main function expects to find 'settings.json' in current directory with an object
with the following attributes:
   - apiKey - string with API key under which to create rules
   - bridge - string with IP address of the bridge
   - otherKeys - array of strings with other keys which should not be reported as foreign
     (e.g., other apps used to set up rules)
'''

from hue import HueBridge
import json

# Configuration for living room
CONFIG_LR = [
    # State sensor for cycling scenes for the switch
    {
        "type": "state",
        "name": "Wohnzimmer state"
    },
    # Philips Tap switch (built into Eltako frame on the wall)
    {
        "type": "switch",
        "name": "Wohnzimmer switch",
        "bindings": {
            # Redirect to external actions, so we can use more than one switch
            "tr": { "type": "redirect", "value": "14" },
            "br": { "type": "redirect", "value": "12" },
            # Use one button to turn off kitchen light from the living room (external input 11)
            "bl": { "type": "redirect", "value": "11" },
            # Use both top buttons together to directly switch to bright scene
            "tlr": {
                "type": "scene",
                "group": "Wohnzimmer",
                "value": "Bright",
                # Since we are changing the scene "from the side", explicitly set state to
                # the given value (index of scene in binding 14 below)
                "state": "Wohnzimmer state",
                "setstate": 4
            },
            # Use both bottom buttons together to switch off the light in both living room and kitchen
            "blr": { "type": "redirect", "value": "19" }
        }
    },
    # Smart button to turn on/off the light above the cabinet
    {
        "type": "switch",
        "name": "Bücherregal Button",
        "bindings": {
            "on": { "type": "redirect", "value": "17" },
            "on-hold": { "type": "redirect", "value": "18" },
        }
    },
    # Actions for external input from an Enocean switch (similar to Philips Tap)
    # We also redirect actions from Philips switch above to these actions in order
    # to spare rules created on the bridge and not to duplicate the configuration.
    {
        "type": "external",
        # Name for actions from this input block
        "name": "Wohnzimmer switch",
        # Light group to manage (default for all bindings)
        "group": "Wohnzimmer",
        # State to use for cycling scenes
        "state": "Wohnzimmer state",
        "bindings": {
            # Action for switch on button
            "14": {
                # Use (multi)-scene action for this button
                "type": "scene",
                # force resetting state on off button
                # (to start with the right scene even if nightlight is on)
                "reset": "off",
                # Scenes to cycle through when pushing on button several times
                "configs": [
                    {"scene": "Talk"},
                    {"scene": "TV"},
                    {"scene": "Talk"},
                    {"scene": "Bright"},
                    {"scene": "Vitrine"}
                ],
                # Default scenes for first on button click depending on time of day
                # Indices indicate 1-based index of the scene above in configs.
                "times": {
                    "T07:00:00/T16:00:00": 5,   # during the day
                    "T16:00:00/T07:00:00": 1    # evening/night
                }
            },
            # Actions for switch off button
            "12": [
                # Note list of bindings to associate more than one action
                {
                    "type": "scene",
                    "action": "toggle",
                    "value": "Nacht",
                    "timeout": "00:20:00"   # switch light off after 20 minutes
                },
                # Second action, now at Christmas time to turn off light on the Christmas tree... :-)
                {
                    "type": "light",
                    "light": "Stromček",
                    "action": "off"
                }
            ],
            # Action for button 3, toggle light on the Christmas tree
            "13": {
                "type": "light",
                "light": "Stromček",
                "action": "toggle"
            },
            # Action for switching off both living room and kitchen lights
            "19": {
                "type": "off",
                "group": "Wohnküche",
                "state": "Wohnzimmer state"
            }

            # We also have external action "11" sent by the switch in the living room.
            # Instead of handling it here, it's moved below to kitchen configuration,
            # since it's more natural. But, it could be defined here as well.
        }
    },
    # Light above the cabinet
    {
        "type": "external",
        "group": "Bücherregal",         # group to manage
        "name": "Bücherregal Button",
        "bindings": {
            "17": {
                "type": "scene",
                "value": "Concentrate"
            },
            "18": {
                "type": "off"
            }
        }
    },
    # Contact sensor driven by HomeKit, set when all doors on living room and kitchen closed
    {
        "type": "contact",
        "name": "Wohnküche Tür",
    },
    # Sensor to turn off the light if there is no activity in the dining room or living room
    {
        "type": "motion",
        "name": "Wohnzimmer sensor",
        "sensors": ["Essen sensor", "Wohnzimmer sensor", "Bücherregal sensor"], # use two sensors in parallel
        "contact": "Wohnküche Tür",
        # Assign sensors to the group
        "group": "Wohnzimmer und Essen",
        "lightgroup": "Wohnzimmer",
        "timeout": "00:09:30",
        "dimtime": "00:00:20",
        "state": "Wohnzimmer state",
        "bindings": {}
    }
]

# Configuration for the kitchen (connected with living room)
CONFIG_KITCHEN = [
    # State for cycling the switch
    {
        "type": "state",
        "name": "Küche state"
    },
    # Philips Tap switch built into Eltako frame on the wall.
    {
        "type": "switch",
        "name": "Küche switch",
        "bindings": {
            "tl": {
                # On action will be redirected to respective external actions, so we can share
                # configuration with motion sensor below.
                "type": "redirect",
                "value": "29"
            },
            "bl": {
                # Off action executed inline.
                "type": "scene",
                "group": "Küche",
                # State will be reset, so next on action will use default state based on time.
                # Note that we have to put state to the binding, else the redirect for living
                # room light off below would reset the state as well.
                "state": "Küche state",
                # Instead of multiple scene configs, we use single scene value here.
                "value": "off"
            },
            "tr": {
                # A button to turn on the light in living room - redirect to action for living
                # room defined above.
                "type": "redirect",
                "value": "14",
            },
            "br": {
                # A button to turn off the light in living room - redirect to action for living
                # room defined above.
                "type": "redirect",
                "value": "12",
            },
            # Use both bottom buttons together to switch off the light in both living room and kitchen
            "blr": { "type": "redirect", "value": "19" }
        }
    },
    # Smart button to turn on/off the light under cabinet
    {
        "type": "switch",
        "name": "Küche Unterlicht",
        "bindings": {
            "on": {
                "type": "scene",                # group action 
                "group": "Küche Unterlicht",    # group to manage
                "value": "Concentrate",         # scene to set
                "action": "toggle"              # toggle between on/off states only (single config)
            },
            "on-hold": {
                "type": "scene",                # group action 
                "group": "Küche Spüle",         # group to manage
                "value": "Concentrate",         # scene to set
                "action": "toggle"              # toggle between on/off states only (single config)
            }
        }
    },
    # Smart button to turn on/off the light above the sink
    {
        "type": "switch",
        "name": "Küche Spüle",
        "bindings": {
            "on": {
                "type": "scene",                # group action 
                "group": "Küche Spüle",         # group to manage
                "value": "Concentrate",         # scene to set
                "action": "toggle"              # toggle between on/off states only (single config)
            },
            "on-hold": {
                "type": "scene",                # group action 
                "group": "Küche Unterlicht",    # group to manage
                "value": "Concentrate",         # scene to set
                "action": "toggle"              # toggle between on/off states only (single config)
            }
        }
    },
    # Definition of external actions for kitchen
    {
        "type": "external",
        "name": "Küche",
        "group": "Küche",
        "state": "Küche state",
        "bindings": {
            # Kitchen binding from above to turn on light, based on time
            "29": {
                "type": "scene",
                # Instead of controlling all lights, only control the main light. The light
                # under the cabinet is untouched.
                "group": "Küche Oberlicht",
                "configs": [
                    {"scene": "Tag"},
                    {"scene": "Concentrate"},
                    {"scene": "Night"},
                    {"scene": "Abend"}
                ],
                "times": {
                    "T06:00:00/T18:00:00": 2,
                    "T18:00:00/T21:30:00": 1,
                    "T21:30:00/T00:30:00": 4,
                    "T00:30:00/T05:00:00": 3,
                    "T05:00:00/T06:00:00": 4
                }
            },
            # Extra action for one of buttons in the living room to turn off light in the kitchen
            "11": {
                # Turn off all lights in the kitchen
                "group": "Küche",
                "type": "off"
            }
        }
    },
    # Motion sensor to control light in the kitchen
    {
        "type": "motion",
        "name": "Küche sensor",     # motion sensor name as defined in Philips app
        "group": "Küche",           # group to control
        "timeout": "00:03:00",      # timeout after no motion detected to dim the light
        "dimtime": "00:00:20",      # timeout to turn off lights after dimming
        "state": "Küche state",     # switch state sensor to reset to activate default action
        "bindings": {
            # On action redirects to the same action as the switch on button
            "on": { "type": "redirect", "value": "29" },
            # It is possible to specify an optional recover action to prevent the need for saving
            # scene state on each dimming (and wearing off the lamps).
            #"recover": { "type": "redirect", "value": "29" },
            # Off action turns off all lights in the kitchen, not only ceiling light
            "off": { "type": "redirect", "value": "11" }
            # We use default dim action to dim by 50% here, so not specified.
        }
    }
]

# Configuration for the dining room (connected with living room)
CONFIG_DINING = [
    # State for cycling the switch
    {
        "type": "state",
        "name": "Essen state"
    },
    # Definition of external actions for dining room
    {
        "type": "external",
        "name": "Essen",
        "group": "Essen",
        "state": "Essen state",
        "bindings": {
            # Turn on the light, based on time
            "71": {
                "type": "scene",
                "configs": [
                    {"scene": "Tag"},
                    {"scene": "Oben"},
                    {"scene": "Concentrate"},
                    {"scene": "Tag"},
                    {"scene": "Oben"},
                    {"scene": "Abend"},
                    {"scene": "TV"},
                    {"scene": "Oben"}
                ],
                "times": {
                    "T06:00:00/T09:00:00": 3,
                    "T09:00:00/T17:00:00": 1,
                    "T17:00:00/T21:00:00": 3,
                    "T21:00:00/T06:00:00": 6
                }
            },
            # Turn off the light above dining table
            "70": {
                "type": "off"
            }
        }
    },
    # Sensor to turn off the light if there is no activity in the kitchen, dining room or living room
    {
        "type": "motion",
        "name": "Essen sensor",
        "sensors": ["Essen sensor", "Küche sensor", "Wohnzimmer sensor", "Bücherregal sensor"], # use two sensors in parallel
        # Assign sensors to the group
        "group": "Küche und Essen",
        "lightgroup": "Essen",
        "timeout": "00:09:30",
        "dimtime": "00:00:20",
        "state": "Essen state",
        "contact": "Wohnküche Tür", # uses the same door sensor as living room
        "bindings": {}
    }
]

# Configuration for home office
CONFIG_AZ = [
    # State for cycling the switch
    {
        "type": "state",
        "name": "Arbeitszimmer state"
    },
    # Contact sensor (driven directly by OpenHAB), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "Arbeitszimmer door contact"
    },
    # We use only external switch here, generating actions 33 and 34 for on/off buttons
    {
        "type": "external",
        "name": "Arbeitszimmer",
        "group": "Arbeitszimmer",
        "state": "Arbeitszimmer state",
        "bindings": {
            # use right side of the switch for on/off action
            "33": {
                "type": "scene",
                "configs": [
                    {"scene": "Bright"},
                    {"scene": "Day"},
                    {"scene": "Concentrate"}
                ],
                "times": {
                    "T06:00:00/T07:45:00": 3,
                    "T07:45:00/T20:00:00": 2,
                    "T20:00:00/T23:00:00": 3,
                    "T23:00:00/T06:00:00": 1
                },
                # force resetting state on off button
                # (to start with the right scene even if nightligh is on)
                "reset": "off"
            },
            "34": {
                "type": "scene",
                "value": "Nightlight",
                "timeout": "00:00:20",
                "action": "toggle"
            },
            # use left side of the switch for dimming the light
            # (hold to dim/brighten, release to stop)
            "31": { "type": "dim", "value": 254, "tt": 35 },
            "32": { "type": "dim", "value": -254, "tt": 35 },
            "-31": { "type": "dim", "value": 0, "tt": 0 },
            "-32": { "type": "dim", "value": 0, "tt": 0 }
        }
    },
    # Motion sensor to turn light on automatically.
    {
        "type": "motion",
        "name": "Arbeitszimmer sensor",
        "group": "Arbeitszimmer",
        "timeout": "00:05:00",
        "dimtime": "00:00:15",
        "state": "Arbeitszimmer state",
        "contact": "Arbeitszimmer door contact",
        "sensors": ["Arbeitszimmer sensor"], # could use more than one sensor here
        "bindings": {
            # Again, redirect via external input to have common code for switch and motion sensor.
            "on": { "type": "redirect", "value": "33" }
            # Note: If we'd use explicit recover action, we could use same action as
            # "on" - shortcut to prevent duplicating the action
            #"recover": "on"
        }
    }
]

# Guest bathroom
CONFIG_WC = [
    # Contact sensor (external one), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "WC door contact",
        "bindings": {
            "open": "1000",
            "closed": "1001"
        } 
    },
    # Switch state for cycling scenes.
    {
        "type": "state",
        "name": "Gäste-WC state"
    },
    # Motion sensor to turn light on automatically.
    {
        "type": "motion",
        "name": "Gäste-WC sensor",
        "group": "Gäste-WC",
        "timeout": "00:00:45",
        "dimtime": "00:00:15",
        "state": "Gäste-WC state",
        # Cooperate with the contact to prevent turning lights on when door is closed and
        # someone is inside (and for instance taking a shower behind glass door, so the
        # sensor doesn't "see" the motion). Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "WC door contact",
        # Force timeout even on closed door contact after 20 minutes. This is a safety net
        # if the contact breaks. Any motion within this time period will reset the timer.
        "closedtimeout": "00:20:00",
        "bindings": {
            # Again, redirect via external input to have common code for switch and motion sensor.
            "on": { "type": "redirect", "value": "108" }
        }
    },
    {
        "type": "external",
        "name": "Gäste-WC",
        "group": "Gäste-WC",
        "state": "Gäste-WC state",
        "bindings": {
            "108": {
                # Scene to set common to switch on and to motion sensor detecting motion.
                # Currently only one scene is set, but to demonstrate redirect, we created
                # additional action. In reality, it would be sufficient to specify the same
                # single-scene action here and in motion sensor definition.
                "type": "scene",
                "configs": [
                    { "scene": "Concentrate"},
                    { "scene": "Nightlight"},
                    { "scene": "Bright"}
                ],
                "times": {
                    "T06:00:00/T23:00:00": 1,
                    "T23:00:00/T00:30:00": 3,
                    "T00:30:00/T05:00:00": 2,
                    "T05:00:00/T06:00:00": 3
                }
            },
            "109": { "type": "off" }
        }
    }
]

# Configuration for the patio
CONFIG_PATIO = [
    {
        "type": "external",
        "name": "Terrasse",
        "group": "Terrasse",
        "bindings": {
            "150": {
                "type": "scene",
                "value": "Concentrate"
            },
            "151": {
                "type": "off"
            }
        }
    }
]

# Hallways
CONFIG_HWEGUG = [
    # This demonstrates two hallways with their respective motion sensor and switches.
    # There are several switches for each hallway, but their actions are mapped to the
    # same external input code, so we need only one set of rules for all of them.
    # All use the same pattern of double-redirect to disable the motion sensor for a short
    # time when pressing the switch and redirecting to the same on action for both switch
    # and motion sensor.

    {
        "type": "motion",
        "name": "Flur sensor",
        "sensors": ["Flur sensor", "Flur sensor 2"], # use two sensors in parallel
        "group": "Flur",
        "timeout": "00:02:00",
        "dimtime": "00:00:20",
        "state": "Flur state",
        "bindings": {
            "on": { "type": "redirect", "value": "102" }
        }
    },
    {
        "type": "state",
        "name": "Flur state"
    },
    {
        "type": "external",
        "name": "Flur",
        "group": "Flur",
        "bindings": {
            # on action redirected from motion sensor above as well
            "102": {
                "type": "scene",
                "state": "Flur state",
                "configs": [
                    {"scene": "Day"},
                    {"scene": "Evening"},
                    {"scene": "Nightlight"},
                    {"scene": "Night"}
                ],
                "times": {
                    "T23:00:00/T00:30:00": 4,
                    "T00:30:00/T05:00:00": 3,
                    "T05:00:00/T06:00:00": 4,
                    "T06:00:00/T18:00:00": 1,
                    "T18:00:00/T23:00:00": 2,
                },
                "reset": "off"
            },
            "103": { "type": "off", "state": "Flur state" },
            "130": { "type": "off", "group": "UG" },
            "131": { "type": "off", "group": "UGEG" }
        }
    },

    {
        "type": "motion",
        "name": "Kellersensor",
        "group": "Kellerflur",
        "timeout": "00:01:30",
        "dimtime": "00:00:20",
        "state": "Kellerflur state",
        "bindings": {
            "on": { "type": "redirect", "value": "106" }
        }
    },
    {
        "type": "state",
        "name": "Kellerflur state"
    },
    {
        "type": "external",
        "name": "Kellerflur",
        "group": "Kellerflur",
        "bindings": {
            # on action redirected from motion sensor above as well
            "106": {
                "type": "scene",
                "state": "Kellerflur state",
                "configs": [
                    {"scene": "Night"},
                    {"scene": "Day"}
                ],
                "times": {
                    "T23:00:00/T06:00:00": 1,
                    "T06:00:00/T23:00:00": 2
                }
            },
            "107": { "type": "off", "state": "Kellerflur state" }
        }
    },
    
    # Additional action for all-off button at the entrance.
    {
        "type": "external",
        "name": "All off",
        "bindings": {
            "2": {
                # Special group "All Lights" addresses as the name says all lights.
                "group": "All Lights",
                "type": "off"
            }
        }
    }
]

CONFIG_HWOG = [
    {
        "type": "motion",
        "name": "Gallerie sensor",
        "group": "Gallerie",
        "timeout": "00:01:30",
        "dimtime": "00:00:20",
        "state": "Gallerie state",
        "bindings": {
            "on": { "type": "redirect", "value": "104" },
            "dim": {
                # Here we use special dimming method. In case we are dimming during the day,
                # then just dim as usual by decreasing the brightness by half (-128/256).
                # But, in the night, the light is alredy at the smallest possible intensity,
                # so instead switch off one of the two lights to simulate dimming (though not
                # optimal, since brightness is logarithmic).
                "type": "scene",
                "configs": [
                    {"scene": "NightDim"},  # this is the scene with only one light on
                    {"scene": "dim", "value": -128}
                ],
                "times": {
                    "T22:00:00/T06:00:00": 1,
                    "W003/T06:00:00/T08:30:00": 1,
                    "W124/T06:00:00/T08:30:00": 2,
                    "T08:30:00/T22:00:00": 2
                }
            }
        }
    },
    {
        "type": "state",
        "name": "Gallerie state"
    },
    {
        "type": "external",
        "name": "Gallerie",
        "group": "Gallerie",
        "bindings": {
            # on action redirected from motion sensor above as well
            "104": {
                "type": "scene",
                "state": "Gallerie state",
                "configs": [
                    {"scene": "Night"},
                    {"scene": "Evening"},
                    {"scene": "Day"}
                ],
                "times": {
                    "T22:00:00/T06:00:00": 1,
                    # on weekends and vacations, only turn on full light starting 8:30
                    "W003/T06:00:00/T08:30:00": 1,
                    "W124/T06:00:00/T08:30:00*1": {"index": 1, "flag": "Vacation", "value": True},
                    # on weekdays, turn on full light starting 6:00
                    "W124/T06:00:00/T08:30:00*2": {"index": 3, "flag": "Vacation", "value": False},
                    "T08:30:00/T20:30:00": 3,
                    "T20:30:00/T22:00:00": 2
                }
            },
            "105": { "type": "off", "state": "Gallerie state" }
        }
    },

    # Additional action for all-off button at the entrance.
    {
        "type": "external",
        "name": "All off",
        "bindings": {
            "2": {
                # Special group "All Lights" addresses as the name says all lights.
                "group": "All Lights",
                "type": "off"
            }
        }
    }
]

# Configuration for first kid's room
CONFIG_KIND1 = [
    # Primary switch (Philips Tap)
    {
        "type": "switch",
        "name": "Julia switch",
        "group": "Julia oben",
        "bindings": {
            # on/off redirected to have only one implementation for switch and dimmer
            "tl": { "type": "redirect", "value": "51" },
            "bl": { "type": "redirect", "value": "52" },
            # remaining buttons used to dim up and down from the primary switch
            "tr": { "type": "dim", "value": 50, "tt": 5 },
            "br": { "type": "dim", "value": -50, "tt": 5 }
        }
    },
    # Secondary switch (Philips Dimmer)
    {
        "type": "switch",
        "name": "Julia dimmer",
        "group": "Julia oben",
        "bindings": {
            # on/off redirected to have only one implementation for switch and dimmer
            "on": { "type": "redirect", "value": "51" },
            "off": { "type": "redirect", "value": "52" },
            # This is a special binding to install standard dimmer rules for
            # continuous dimming down and up using brightness buttons.
            **HueBridge.DIMMER_RULES
        }
    },
    # Contact sensor (external one), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "Julia door contact",
        "bindings": {
            "open": "1020",
            "closed": "1021"
        } 
    },
    # Motion sensor to turn light off automatically.
    {
        "type": "motion",
        "name": "Julia sensor",
        "group": "Julia",
        "timeout": "00:02:45",
        "dimtime": "00:00:15",
        "state": "Julia state",
        # Cooperate with the contact to prevent turning lights off when door is closed and
        # someone is inside. Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "Julia door contact",
        # Force timeout even on closed door contact after 20 minutes. This is a safety net
        # if the contact breaks. Any motion within this time period will reset the timer.
        "closedtimeout": "00:20:00",
        "bindings": {
            # no bindings, just turn the light off after timeout
        },
        # Turn off the sensor at the specified time.
        # Turning off the light afterwards will reactivate it.
        # Turning on the light using the switch will also reactivate it (see sensor_on).
        "sensor_off": "W124/T05:00:00"
    },
    {
        "type": "state",
        "name": "Julia state",
        "timeout": "00:00:10@off",
        "group": "Julia"
    },
    # Actual actions for on/off
    {
        "type": "external",
        "name": "Julia",
        "group": "Julia oben",
        "state": "Julia state",
        "bindings": {
            "51": {
                "type": "scene",
                "state": "Julia state",
                "reset": "off",
                "sensor_on": "Julia sensor",
                "configs": [
                    {"scene": "Concentrate"},
                    {"scene": "Read"},
                    {"scene": "Bunt"}
                ],
                "times": {
                    "T06:00:00/T20:00:00": 1,
                    "T20:00:00/T06:00:00": 2
                }
            },
            "52": {
                "type": "scene",
                # turn off *all* the lights, not just at the top
                "group": "Julia",
                # When in second state (night light), turn off after 20 minutes
                "value": "Nachtlicht",
                "timeout": "00:20:00",
                "action": "toggle",
                # Turn off the sensor for this toggle when the night light is switched on
                # to prevent turning off the night light via sensor timeout. The sensor will
                # reactivate itself after the light is turned off.
                "sensor_off": "Julia sensor"
            }
        }
    }
]

# Configuration for second kid's room
CONFIG_KIND2 = [
    # Primary switch (Philips Tap)
    {
        "type": "switch",
        "name": "Katarina switch",
        "group": "Katarina",
        "bindings": {
            # Redirected to on/off actions from a secondary switch (routed from
            # an Enocean switch via external input).
            "tl": { "type": "redirect", "value": "42" },
            "bl": { "type": "redirect", "value": "41" },
            # remaining buttons used to dim up and down from the primary switch
            "tr": { "type": "dim", "value": 50, "tt": 5 },
            "br": { "type": "dim", "value": -50, "tt": 5 }
        }
    },
    # Contact sensor (driven directly by HomeKit), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "Katarina door contact"
    },
    # Motion sensor to turn light off automatically.
    {
        "type": "motion",
        "name": "Katarina sensor",
        "group": "Katarina",
        "timeout": "00:02:45",
        "dimtime": "00:00:15",
        "state": "Katarina state",
        # Cooperate with the contact to prevent turning lights off when door is closed and
        # someone is inside. Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "Katarina door contact",
        # Force timeout even on closed door contact after 40 minutes. This is a safety net
        # if the contact breaks. Any motion within this time period will reset the timer.
        "closedtimeout": "00:40:00",
        "bindings": {
            # no bindings, just turn the light off after timeout
        },
        # Turn off the sensor at the specified time.
        # Turning off the light afterwards will reactivate it.
        # Turning on the light using the switch will also reactivate it (see sensor_on).
        "sensor_off": "W124/T05:00:00"
    },
    {
        "type": "state",
        "name": "Katarina state",
        "timeout": "00:00:10@off",
        "group": "Katarina"
    },
    {
        "type": "external",
        "name": "Katarina",
        "group": "Katarina",
        "state": "Katarina state",
        # on/off actions, triggered via redirect from primary switch and directly from secondary switch
        "bindings": {
            "42": {
                "type": "scene",
                "state": "Katarina state",
                "reset": "off",
                "sensor_on": "Katarina sensor",
                "configs": [
                    {"scene": "Hell"},
                    {"scene": "Lesen"},
                    {"scene": "Bunt"}
                ],
                "times": {
                    "T06:00:00/T20:00:00": 1,
                    "T20:00:00/T06:00:00": 2
                }
            },
            "41": {
                "type": "scene",
                "value": "Nachtlicht", 
                "timeout": "00:20:00",
                "action": "toggle",
                "sensor_off": "Katarina sensor",
            }
        }
    }
]

# Configuration for the bedroom
CONFIG_B = [
    # Primary switch (Philips Tap)
    {
        "type": "switch",
        "name": "Schlafzimmer switch",
        "group": "Schlafzimmer",
        "bindings": {
            "tr": { "type": "redirect", "value": "61" },
            "br": { "type": "redirect", "value": "62" },
            "tl": { "type": "dim", "value": 50, "tt": 5 },
            "bl": { "type": "dim", "value": -50, "tt": 5 }
        }
    },
    # Secondary switch (Philips Dimmer)
    {
        "type": "switch",
        "name": "Schlafzimmer D1",
        "group": "Schlafzimmer",
        "bindings": {
            "on": { "type": "redirect", "value": "61" },
            "off": { "type": "redirect", "value": "62" },
            **HueBridge.DIMMER_RULES
        }
    },
    # Tertiary switch (Philips Dimmer)
    {
        "type": "switch",
        "name": "Schlafzimmer D2",
        "group": "Schlafzimmer",
        "bindings": {
            "on": { "type": "redirect", "value": "61" },
            "off": { "type": "redirect", "value": "62" },
            **HueBridge.DIMMER_RULES
        }
    },
    # Contact sensor (driven directly by HomeKit), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "Schlafzimmer door contact"
    },
    # Motion sensor to turn light off automatically.
    {
        "type": "motion",
        "name": "Schlafzimmer sensor",
        "group": "Schlafzimmer",
        "timeout": "00:04:45",
        "dimtime": "00:00:15",
        "state": "Schlafzimmer state",
        # Cooperate with the contact to prevent turning lights off when door is closed and
        # someone is inside. Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "Schlafzimmer door contact",
        # Force timeout even on closed door contact after 40 minutes. This is a safety net
        # if the contact breaks. Any motion within this time period will reset the timer.
        "closedtimeout": "00:40:00",
        "bindings": {
            # no bindings, just turn the light off after timeout
        },
        # Turn off the sensor at the specified time.
        # Turning off the light afterwards will reactivate it.
        # Turning on the light using the switch will also reactivate it (see sensor_on).
        "sensor_off": "W124/T05:00:00"
    },
    {
        "type": "state",
        "name": "Schlafzimmer state",
        "timeout": "00:00:10@off",
        "group": "Schlafzimmer"
    },
    # on/off actions redirected from primary, secondary and tertiary switch
    {
        "type": "external",
        "name": "Schlafzimmer",
        "group": "Schlafzimmer",
        "state": "Schlafzimmer state",
        "bindings": {
            "61": {
                "type": "scene",
                "reset": "off",
                "sensor_on": "Schlafzimmer sensor",
                "configs": [
                    {"scene": "Concentrate"},
                    {"scene": "Relax"},
                    {"scene": "Bright"},
                    {"scene": "Evening"},
                    {"scene": "Relax"},
                    {"scene": "Read"}
                ],
                "times": {
                    "T06:00:00/T20:00:00": 1,
                    "T20:00:00/T22:00:00": 4,
                    "T22:00:00/T06:00:00": 5
                }
            },
            "62": {
                "type": "scene",
                "value": "Nightlight", 
                "timeout": "00:20:00",
                "action": "toggle",
                "sensor_off": "Schlafzimmer sensor",
            }
        }
    }
]

# Configuration for the bathroom
CONFIG_BAD = [
    # Switch state for cycling scenes.
    {
        "type": "state",
        "name": "Badezimmer state",
        "timeout": "00:00:10@off",
        "group": "Badezimmer"
    },
    # Primary switch (Philips Tap)
    {
        "type": "switch",
        "name": "Badezimmer switch",
        "group": "Badezimmer",
        "bindings": {
            "tl": { "type": "redirect", "value": "65" },
            "bl": { "type": "redirect", "value": "66" },
            "tr": { "type": "light", "light": "Badezimmer Spiegel", "action": "on" },
            "br": { "type": "light", "light": "Badezimmer Spiegel", "action": "off" },
            "tlr": {
                "type": "scene",
                "group": "Badezimmer",
                "value": "Bright",
                # Since we are changing the scene "from the side", explicitly set state to
                # the given value (index of scene in binding 14 below)
                "state": "Badezimmer state",
                "setstate": 1
            }
        }
    },
    # Contact sensor (external one), to detect whether the door is open or closed.
    {
        "type": "contact",
        "name": "Badezimmer contact",
        "bindings": {
            "open": "1010",
            "closed": "1011"
        }
    },
    # Motion sensor to turn light on automatically.
    {
        "type": "motion",
        "name": "Badezimmer sensor",
        "group": "Badezimmer",
        "timeout": "00:02:00",
        "dimtime": "00:00:30",
        "state": "Badezimmer state",
        # Cooperate with the contact to prevent turning lights on when door is closed and
        # someone is inside (and for instance taking a shower behind glass door, so the
        # sensor doesn't "see" the motion). Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "Badezimmer contact",
        "bindings": {
            # Again, redirect via external input to have common code for switch and motion sensor.
            "on": { "type": "redirect", "value": "65" }
        }
    },
    # on/off actions redirected from primary switch and motion sensor.
    {
        "type": "external",
        "name": "Badezimmer",
        "group": "Badezimmer",
        "state": "Badezimmer state",
        "bindings": {
            "65": {
                "type": "scene",
                "group": "Badezimmer oben",
                "configs": [
                    {"scene": "Day"},
                    {"scene": "Evening"},
                    {"scene": "Nightlight"},
                    {"scene": "Evening"}
                ],
                "times": {
                    "T21:00:00/T00:00:00": 4,
                    "T00:00:00/T06:00:00": 3,
                    # on weekdays, use dimmed light between 6:00 and 6:30 and full light from 6:30 on
                    "W124/T06:00:00/T06:30:00": {"index": 4, "flag": "Vacation", "value": False},
                    "W124/T06:30:00/T08:30:00": {"index": 1, "flag": "Vacation", "value": False},
                    # on weekends and vacations, use night light until 7:30 and dimmed light between 7:30 and 8:30
                    "W003/T06:00:00/T07:30:00": 3,
                    "W003/T07:30:00/T08:30:00": 4,
                    "W124/T06:00:00/T07:30:00": {"index": 3, "flag": "Vacation", "value": True},
                    "W124/T07:30:00/T08:30:00": {"index": 4, "flag": "Vacation", "value": True},
                    # always full light from 8:30 on
                    "T08:30:00/T21:00:00": 1
                }
            },
            "66": {
                "type": "off"
            }
        }
    }
]

# Configuration for utility room
CONFIG_HWR = [
    # Only one motion sensor in this room to turn light on/off
    {
        "type": "motion",
        "name": "HWR Sensor",
        "group": "HWR",
        "timeout": "00:03:00",
        "dimtime": "00:00:20",
        "bindings": {
            "on": { "type": "redirect", "value": "112" }
        }
    },
    # on/off actions redirected from switch and motion sensor.
    {
        "type": "external",
        "name": "HWR",
        "group": "HWR",
        "bindings": {
            "112": {
                "type": "scene",
                "value": "Bright"
            },
            "113": {
                "type": "off"
            }
        }
    }
]

# Configuration for the basement
CONFIG_BASEMENT = [
    # Motion sensor to turn light on automatically.
    {
        "type": "motion",
        "name": "Werk sensor",
        "group": "Keller",
        "timeout": "00:03:00",
        "dimtime": "00:00:15",
        "bindings": {
            "on": { "type": "redirect", "value": "110" }
        }
    },
    # on/off actions redirected from switch and motion sensor.
    {
        "type": "external",
        "name": "Keller",
        "group": "Keller",
        "bindings": {
            "110": {
                "type": "scene",
                "value": "Concentrate"
            },
            "111": {
                "type": "off"
            }
        }
    }
]

# Configuration for room in basement
CONFIG_HOBBY = [
    # Switch (Philips Dimmer)
    {
        "type": "switch",
        "name": "Hobbyraum switch",
        "group": "Hobbyraum",
        "bindings": {
            "on": { "type": "redirect", "value": "121" },
            "off": { "type": "redirect", "value": "122" },
            **HueBridge.DIMMER_RULES
        }
    },
    # Motion sensor in this room to turn light on/off
    {
        "type": "motion",
        "name": "Hobbyraum sensor",
        "group": "Hobbyraum",
        "timeout": "00:03:00",
        "dimtime": "00:00:20",
        "bindings": {
            "on": { "type": "redirect", "value": "121" }
        }
    },
    {
        "type": "state",
        "name": "Hobbyraum state",
        "timeout": "00:00:10@off",
        "group": "Hobbyraum"
    },
    # on/off actions redirected from switch and motion sensor.
    {
        "type": "external",
        "name": "Hobbyraum",
        "group": "Hobbyraum",
        "state": "Hobbyraum state",
        "bindings": {
            "121": {
                "type": "scene",
                "reset": "off",
                "configs": [
                    {"scene": "Concentrate"},
                    {"scene": "Bright"},
                    {"scene": "Relax"},
                    {"scene": "Read"},
                    {"scene": "Relax"}
                ],
                "times": {
                    "T06:00:00/T20:00:00": 1,
                    "T20:00:00/T22:00:00": 4,
                    "T22:00:00/T06:00:00": 5
                }
            },
            "122": {
                "type": "scene",
                "value": "Nightlight", 
                "timeout": "00:20:00",
                "action": "toggle"
            }
        }
    }
]

# Test config for wake up (not yet working correctly)
CONFIG_TEST = [
    {
        "type": "wakeup",
        "name": "Test",
        "group": "WC Wakeup",
        "start": "W124/T06:20:00",
        "duration": 10, # minutes
        "offtime": 60  # minutes since wakeup done
    }
]

# Boot rule configuration to turn off lights on boot
CONFIG_BOOT = [ { "type": "boot" } ]

if __name__ == '__main__':
    # load the bridge and key configuration from settings.json
    config = {}
    with open("settings.json", "r") as configFile:
        config = json.loads(configFile.read())

    h = HueBridge(config["bridge"], config["apiKey"])

    # run configuration on individual resources/rooms
    h.configure(CONFIG_LR, "Wohnzimmer")
    h.configure(CONFIG_KITCHEN, "Küche")
    h.configure(CONFIG_DINING, "Esszimmer")
    h.configure(CONFIG_AZ, "Arbeitszimmer")
    h.configure(CONFIG_WC, "Gäste-WC")
    h.configure(CONFIG_PATIO, "Terrasse")
    h.configure(CONFIG_HWEGUG, "Flure")
    h.configure(CONFIG_HWR, "HWR")
    h.configure(CONFIG_BASEMENT, "Keller")
    h.configure(CONFIG_HOBBY, "Hobbyraum")
    #h.configure(CONFIG_TEST, "Test")    # not yet working correctly
    #h.configure(CONFIG_BOOT, "Boot")    # not yet working correctly

    # refresh configuration from the bridge and report any foreign rules
    #h.refresh()
    #h.findForeignData(config["otherKeys"])
    #h.fixLightScenes(False) # fix light scenes to be normal group scenes where possible (except wakeup and co)
    #h.fixSceneAppData(False) # fix appdata of scenes (if passed True) to properly display in the app
    #h.findUnusedLightScenes(False) # find (and delete, if passed True) scenes, which are not used anymore
    #h.listAll()

    if "bridge2" in config:
        # Example with second bridge to control further rooms
        print("Processing second bridge")
        h = HueBridge(config["bridge2"], config["apiKey2"])
        h.configure(CONFIG_HWOG, "Gallerie")
        h.configure(CONFIG_B, "Schlafzimmer")
        h.configure(CONFIG_KIND1, "Julia")
        h.configure(CONFIG_KIND2, "Katarina")
        h.configure(CONFIG_BAD, "Badezimmer")
        #h.refresh()
        #h.findForeignData(config["otherKeys"])
        #h.fixLightScenes(False) # fix light scenes to be normal group scenes where possible (except wakeup and co)
        #h.fixSceneAppData(False) # fix appdata of scenes (if passed True) to properly display in the app
        #h.findUnusedLightScenes(False) # find (and delete, if passed True) scenes, which are not used anymore
        #h.listAll()
