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
        "name": "Wohnzimmer state",
        # We have two different cycles - one for on and one for off button, so 2 uses.
        # This is not strictly needed, only if state timeout is used, it indicates how
        # many reset rules to create.
        "uses": 2,
        # reset the state after small timeout, but only if lights are off
        "timeout": "00:00:10@off",
        # group is necessary to tell it which lights to check
        "group": "Wohnzimmer"
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
            }
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
        "bindings": {
            # Action for switch on button
            "14": {
                # State to use for cycling scenes
                "state": "Wohnzimmer state",
                # Use (multi)-scene action for this button
                "type": "scene",
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
                    # State to use for cycling scenes
                    "state": "Wohnzimmer state",
                    # use negative states in the same state sensor for cycling scenes
                    "stateUse": "secondary",
                    "type": "scene",
                    "configs": [
                        {"scene": "off"},
                        {
                            "scene": "Nacht",
                            "timeout": "00:20:00"   # switch light off after 20 minutes
                        }
                    ]
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
            }

            # We also have external action "11" sent by the switch in the living room.
            # Instead of handling it here, it's moved below to kitchen configuration,
            # since it's more natural. But, it could be defined here as well.
        }
    }
]

# Configuration for the kitchen (connected with living room)
CONFIG_KITCHEN = [
    # State for cycling the switch
    {
        "type": "state",
        "name": "Küche state"
        # We have only one cycle for on button.
        # This is not needed, since single-cycle is default. Also, if state timeout is
        # not used, no reset rules are created, so it's also not needed.
        #"uses": 1
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
            }
        }
    },
    # Definition of external actions for kitchen
    {
        "type": "external",
        "name": "Küche",
        "group": "Küche",
        "bindings": {
            # Action to toggle the light under the cabinet. Does not modify switch state.
            "22": { 
                "type": "light",                # single-light action as opposed to group action 
                "light": "Küche Unterlicht",    # light name to manage
                "action": "toggle"              # toggle between on/off states
            },
            # Kitchen binding from above to turn on light, based on time
            "29": {
                "type": "scene",
                # Instead of controlling all lights, only control the main light. The light
                # under the cabinet is untouched.
                "group": "Küche oben",
                # Note: we need to put state here, otherwise cabinet light toggle above would
                # reset the state as well, which we don't want.
                "state": "Küche state",
                "configs": [
                    {"scene": "Tag"},
                    {"scene": "Concentrate"},
                    {"scene": "Abend"}
                ],
                "times": {
                    "T06:00:00/T18:00:00": 2,
                    "T18:00:00/T21:30:00": 1,
                    "T21:30:00/T06:00:00": 3
                }
            },
            # Extra action for one of buttons in the living room to turn off light in the kitchen
            "11": {
                # Group specified for this binding only - all lights in the kitchen
                "group": "Küche",
                "type": "off",
                "state": "Küche state"
            }
        }
    },
    # Motion sensor to control light in the kitchen
    {
        "type": "motion",
        "name": "Küche sensor",     # motion sensor name as defined in Philips app
        "group": "Küche",           # group to control (for default off action)
        "timeout": "00:03:00",      # timeout after no motion detected to dim the light
        "dimtime": "00:00:20",      # timeout to turn off lights after dimming
        "state": "Küche state",     # switch state sensor to reset to activate default action
        "bindings": {
            # On action redirects to the same action as the switch on button
            "on": { "type": "redirect", "value": "29" },
            # Specify optional recover action to prevent the need for saving scene state
            # on each dimming (and wearing off the lamps). We use default dim action here.
            "recover": { "type": "redirect", "value": "29" }
            # No need to specify off action, it's the default
            #"off": { "type": "off" }
        }
    }
]

# Configuration for home office
CONFIG_AZ = [
    # State for cycling the switch
    {
        "type": "state",
        "name": "Arbeitszimmer state"
    },
    # We use only external switch here, generating actions 33 and 34 for on/off buttons
    {
        "type": "external",
        "name": "Arbeitszimmer",
        "group": "Arbeitszimmer",
        "state": "Arbeitszimmer state",
        "bindings": {
            "33": {
                "type": "scene",
                "configs": [
                    {"scene": "Bright"},
                    {"scene": "Concentrate"}
                ],
                "times": {
                    "T06:00:00/T23:00:00": 2,
                    "T23:00:00/T06:00:00": 1
                }
            },
            "34": {
                "type": "scene",
                "value": "off"
            }
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
        "bindings": {
            # Again, redirect via external input to have common code for switch and motion sensor.
            "on": { "type": "redirect", "value": "108" },
            # Use same action as "on" - shortcut to prevent duplicating the action
            "recover": "on"
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
                    { "scene": "Bright"}
                ],
                "times": {
                    "T06:00:00/T23:00:00": 1,
                    "T23:00:00/T06:00:00": 2
                }
            },
            "109": { "type": "off" }
        }
    }
]

# Hallways
CONFIG_HW = [
    # This demonstrates three hallways with their respective motion sensor and switches.
    # There are several switches for each hallway, but their actions are mapped to the
    # same external input code, so we need only one set of rules for all of them.
    # All use the same pattern of double-redirect to disable the motion sensor for a short
    # time when pressing the switch and redirecting to the same on action for both switch
    # and motion sensor.

    {
        "type": "motion",
        "name": "Flur sensor",
        "group": "Flur",
        "timeout": "00:02:00",
        "dimtime": "00:00:20",
        "state": "Flur state",
        "bindings": {
            "on": { "type": "redirect", "value": "102" },
            "recover": "on"
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
                    {"scene": "Night"},
                    {"scene": "Evening"},
                    {"scene": "Day"}
                ],
                "times": {
                    "T23:00:00/T06:00:00": 1,
                    "T06:00:00/T18:00:00": 3,
                    "T18:00:00/T23:00:00": 2,
                }
            },
            "103": { "type": "off", "state": "Flur state" }
        }
    },

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
                    "T23:00:00/T06:00:00": 1,
                    "T06:00:00/T23:00:00": 2
                }
            },
            "recover": "on"
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
                    "T23:00:00/T06:00:00": 1,
                    "T06:00:00/T20:30:00": 3,
                    "T20:30:00/T23:00:00": 2
                }
            },
            "105": { "type": "off", "state": "Gallerie state" }
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
            "on": { "type": "redirect", "value": "106" },
            "recover": "on"
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

# Configuration for first kid's room
CONFIG_KIND1 = [
    # Primary switch (Philips Tap)
    {
        "type": "switch",
        "name": "Julia switch",
        "group": "Julia",
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
        "group": "Julia",
        "bindings": {
            # on/off redirected to have only one implementation for switch and dimmer
            "on": { "type": "redirect", "value": "51" },
            "off": { "type": "redirect", "value": "52" },
            # This is a special binding to install standard dimmer rules for
            # continuous dimming down and up using brightness buttons.
            **HueBridge.DIMMER_RULES
        }
    },
    {
        "type": "state",
        "name": "Julia state",
        "uses": 2,
        "timeout": "00:00:10@off",
        "group": "Julia"
    },
    # Actual actions for on/off
    {
        "type": "external",
        "name": "Julia",
        "group": "Julia",
        "state": "Julia state",
        "bindings": {
            "51": {
                "type": "scene",
                "state": "Julia state",
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
                "stateUse": "secondary",
                "configs": [
                    {"scene": "off"},
                    # When in second state (night light), turn off after 20 minutes
                    {"scene": "Nachtlicht", "timeout": "00:20:00"}
                ]
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
    {
        "type": "state",
        "name": "Katarina state",
        "uses": 2,
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
                "stateUse": "secondary",
                "configs": [
                    {"scene": "off"},
                    {"scene": "Nachtlicht", "timeout": "00:20:00"}
                ]
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
    {
        "type": "state",
        "name": "Schlafzimmer state",
        "uses": 2,
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
                "configs": [
                    {"scene": "Concentrate"},
                    {"scene": "Bright"},
                    {"scene": "Evening"},
                    {"scene": "Relax"},
                    {"scene": "Read"}
                ],
                "times": {
                    "T06:00:00/T20:00:00": 1,
                    "T20:00:00/T22:00:00": 3,
                    "T22:00:00/T06:00:00": 4
                }
            },
            "62": {
                "type": "scene",
                "stateUse": "secondary",
                "configs": [
                    {"scene": "off"},
                    {"scene": "Nightlight", "timeout": "00:20:00"}
                ]
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
        "uses": 2,
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
            "tr": { "type": "light", "light": "Badezimmer Spiegel", "action": "toggle" },
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
        # Unfortunately, problems with receipt of EnOcean door switch sensor, so for now high timeouts to work as without the contact switch
        "timeout": "00:30:00",
        "dimtime": "00:02:00",
        "state": "Badezimmer state",
        # Cooperate with the contact to prevent turning lights on when door is closed and
        # someone is inside (and for instance taking a shower behind glass door, so the
        # sensor doesn't "see" the motion). Similarly, if there is no motion whatsoever after
        # closing the door, turn lights off shortly after.
        "contact": "Badezimmer contact",
        "bindings": {
            # Again, redirect via external input to have common code for switch and motion sensor.
            "on": { "type": "redirect", "value": "65" },
            "recover": "on"
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
                    "T06:00:00/T07:00:00": 4,
                    "T07:00:00/T21:00:00": 1
                }
            },
            "66": {
                "type": "scene",
                "group": "Badezimmer",
                "stateUse": "secondary",
                "configs": [
                    {"scene": "off"},
                    {"scene": "Nightlight", "timeout": "00:10:00"}
                ]
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
            "on": { "type": "scene", "value": "Bright" },
            "recover": "on"
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
    h.configure(CONFIG_AZ, "Arbeitszimmer")
    h.configure(CONFIG_WC, "Gäste-WC")
    h.configure(CONFIG_HW, "Flure")
    h.configure(CONFIG_KIND1, "Julia")
    h.configure(CONFIG_KIND2, "Katarina")
    h.configure(CONFIG_B, "Schlafzimmer")
    h.configure(CONFIG_BAD, "Badezimmer")
    h.configure(CONFIG_HWR, "HWR")
    #h.configure(CONFIG_TEST, "Test")    # not yet working correctly
    #h.configure(CONFIG_BOOT, "Boot")    # not yet working correctly

    # refresh configuration from the bridge and report any foreign rules
    #h.refresh()
    #h.findForeignData(config["otherKeys"])
    #h.listAll()
