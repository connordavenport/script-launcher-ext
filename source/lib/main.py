# shortCut  : command + d
# menuTitle : Robocast

import os
from thefuzz import fuzz  # noqa: F401
import vanilla
import plistlib
import configparser
from AppKit import NSScreen, NSColor
import AppKit
from mojo.UI import StatusInteractivePopUpWindow, OpenScriptWindow, getDefault
from mojo.tools import ScriptRunner as runner
import subprocess

from lib.UI import preferences
from AppKit import (
    NSEventModifierFlagCommand,
    NSEventModifierFlagShift,
    NSEventModifierFlagOption,
    NSEventModifierFlagControl,
)
from lib.eventTools.eventManager import (
    EventManager,
    getToolOrder,
    setActiveEventToolByIndex,
)

MODIFIER_SYMBOLS = {
    "shift": "⇧",
    "control": "⌃",
    "option": "⌥",
    "command": "⌘",
}


class Robocast(object):
    def __init__(self):

        ## Preference Files
        self.lastScriptFile = os.path.join(
            "/".join(os.path.realpath(__file__).split("/")[:-1]), "lastscript.ini"
        )
        self.preferencesFile = os.path.join(
            "/".join(os.path.realpath(__file__).split("/")[:-1]), "preferences.ini"
        )

        ## Preference Defaults
        self.scriptsDirectory = os.path.join(
            os.getenv("HOME"), "Library/Application Support/RoboFont/scripts"
        )
        self.extensionsDirectory = os.path.join(
            os.getenv("HOME"), "Library/Application Support/RoboFont/plugins"
        )
        self.rememberLast = 1
        self.searchLocal = False
        self.searchUpDir = 3
        self.editor = "robofont"
        # Storage
        self.scripts = {"preferences": ("", "system"), "shortcuts": ("", "system")}

        ## Window
        width = 500
        height = 200

        self.icon_size = 25

        screen = NSScreen.mainScreen()
        screenRect = screen.frame()
        (screenX, screenY), (screenW, screenH) = screenRect
        screenY = -(screenY + screenH)  # convert to vanilla coordinate system
        x = screenX + ((screenW - width) / 2)
        y = screenY + ((screenH - height) / 2)

        self.readPreferences()

        if self.displayToolbar:
            height = 260

        self.w = StatusInteractivePopUpWindow((x, y, width, height), screen=screen)

        self.w.search_box = vanilla.EditText(
            (10, 10, -10, 30), "", placeholder="Search...", callback=self.searchScripts
        )

        self.w.search_box.getNSTextField().setFont_(
            AppKit.NSFont.systemFontOfSize_weight_(24, AppKit.NSFontWeightLight)
        )

        text_ns = self.w.search_box.getNSTextField()
        text_ns.setBordered_(False)
        text_ns.setFocusRingType_(1)
        text_ns.setCornerRadius_(7)
        text_ns.setBackgroundColor_(NSColor.clearColor())

        """using EditText because SearchBox overrides tab and Enter buttons"""
        self.w.list = vanilla.List(
            (10, 50, -10, -65 if self.displayToolbar else -30),
            [],
            columnDescriptions=[{"title": "name"}, {"title": "desc", "width": 120}],
            showColumnTitles=False,
            allowsMultipleSelection=0,
            doubleClickCallback=self.runScript,
        )

        table_ns = self.w.list.getNSTableView()
        table_ns.setUsesAlternatingRowBackgroundColors_(False)
        table_ns.setBackgroundColor_(NSColor.clearColor())
        table_ns.setFocusRingType_(1)
        table_ns.setCornerRadius_(2)
        self.w.list.getNSScrollView().setCornerRadius_(10)

        text = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            "⏎ : Run Script    ⌘ ⏎ : Open Script    ⌘ ⌥ , : Preferences",
            {
                AppKit.NSForegroundColorAttributeName: NSColor.tertiaryLabelColor(),
                AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(
                    12, AppKit.NSFontWeightLight
                ),
            },
        )
        self.w.label = vanilla.TextBox((10, -20, -10, 17), text)

        if self.displayToolbar:
            limit = 15
            if 0 < self.limitToolbar < 15:
                limit = self.limitToolbar
            to_use = EventManager.getOrderedEvents()[:limit]
            for index, event in enumerate(to_use):
                image = event.getToolbarIcon().copy()
                image.resizeTo_(self.icon_size)
                image.setTemplate_(True)

                vv = ((width - (10 + 10)) / len(to_use)) - self.icon_size
                # print(vv)
                var = exec(f"""self.w.button_{type(event).__name__} = vanilla.ImageButton(
                    (({self.icon_size + vv}*index)+10, 200, self.icon_size, self.icon_size),
                    imageObject=image,
                    callback=self.contentCallback,
                    bordered=False,
                )
                """)  # noqa: F841
                exec(
                    f"self.w.button_{type(event).__name__}.identifier = '{type(event).__name__}'"
                )

        # off Window

        self.w.ok_button = vanilla.Button(
            (10, 300, -10, 20), "Run Script", callback=self.runScript
        )

        self.w.closeWindow_button = vanilla.Button(
            (10, 300, -10, 20), "Close Window", callback=self.closeWindow
        )
        self.w.prev_button = vanilla.Button(
            (10, 300, -10, 20), "up", callback=self.previousScript
        )
        self.w.next_button = vanilla.Button(
            (10, 300, -10, 20), "down", callback=self.nextScript
        )
        self.w.scriptingWindow_button = vanilla.Button(
            (10, 300, -10, 20),
            "Open in ScriptingWindow",
            callback=self.openScriptInScriptingWindow,
        )

        self.w.openPrefs_button = vanilla.Button(
            (10, 300, -10, 20), "Preferences", callback=self.openPrefs
        )

        self.lastScriptRead()

        # Bindings
        self.w.prev_button.bind("uparrow", [])
        self.w.next_button.bind("downarrow", [])
        self.w.setDefaultButton(self.w.ok_button)
        self.w.closeWindow_button.bind(chr(27), [])  # esc
        self.w.openPrefs_button.bind(",", ["command", "option"])

        open_script = self.w.scriptingWindow_button.getNSButton()
        open_script.setKeyEquivalent_("\r")
        open_script.setKeyEquivalentModifierMask_(AppKit.NSEventModifierFlagCommand)

        self.w.getNSWindow().makeFirstResponder_(self.w.search_box.getNSTextField())
        self.w.open()

        # DockerController(self.w)

    def contentCallback(self, sender):
        idr = sender.identifier
        idx = getToolOrder().index(idr)
        if idx is not None:
            setActiveEventToolByIndex(idx)
            self.w.close()

    # # # # # # # #
    # PREFERENCES
    # # # # # # # #

    def openPrefs(self, sender):
        # self.d.toggle()
        if os.path.exists(self.preferencesFile):
            subprocess.call(("open", self.preferencesFile))

    def readPreferences(self):
        # Read the preferences file which contains custom paths (scripts/extensions) and other preferential stuff.
        if os.path.exists(self.preferencesFile):
            config = configparser.ConfigParser()
            config.read(self.preferencesFile)

            if "display" in config["TOOLS"]:
                self.displayToolbar = (
                    False
                    if [config["TOOLS"]["display"]][0].lower() == "false"
                    else True
                )
            if "limit" in config["TOOLS"]:
                self.limitToolbar = int([config["TOOLS"]["limit"]][0])
            if "scriptsDir" in config["PATHS"]:
                self.scriptsDirectory = [config["PATHS"]["scriptsDir"]][0]
            if "extensionsDir" in config["PATHS"]:
                self.extensionsDirectory = [config["PATHS"]["extensionsDir"]][0]
            if "rememberLast" in config["REMEMBER"]:
                self.rememberLast = int([config["REMEMBER"]["rememberLast"]][0])
            if "value" in config["SEARCHLOCAL"]:
                self.searchLocal = int([config["SEARCHLOCAL"]["value"]][0])
            if "textEditor" in config["EDITOR"]:
                self.editor = str([config["EDITOR"]["textEditor"]][0]).lower()
            if "searchUpDir" in config["SEARCHLOCAL"]:
                self.searchUpDir = int([config["SEARCHLOCAL"]["searchUpDir"]][0])

        self.searchAll()

    # LAST SCRIPT
    # Read/Write remembers the last script that was run so it can be quickly re-run

    def lastScriptCreate(self):
        if not os.path.exists(self.lastScriptFile):
            config = configparser.ConfigParser()
            config["DEFAULT"]["lastFiles"] = ""
            with open(self.lastScriptFile, "w") as configfile:
                config.write(configfile)

    def lastScriptRead(self):
        if os.path.exists(self.lastScriptFile):
            config = configparser.ConfigParser()
            config.read(self.lastScriptFile)
            l = config["DEFAULT"]["lastFiles"]
            l = l.split(",")
            l = [{"name": i, "desc": "script"} for i in l]
            self.w.list.set(l)
            self.w.list.setSelection([0])
        else:
            self.lastScriptCreate()

    def lastScriptWrite(self, sender, file):
        if file != None:
            config = configparser.ConfigParser()
            config.read(self.lastScriptFile)

            l = config["DEFAULT"]["lastFiles"]
            l = l.split(",")
            if file.split("/")[-1] in l:
                l.remove(file.split("/")[-1])
            l.insert(0, file.split("/")[-1])
            l = l[: self.rememberLast]
            config["DEFAULT"]["lastFiles"] = ",".join(l)

            with open(self.lastScriptFile, "w") as configfile:
                config.write(configfile)

    # # # # # # # #
    # FUNCTIONS
    # # # # # # # #

    def searchAll(self):
        self.scripts = {"preferences": ("", "system"), "shortcuts": ("", "system")}
        if self.searchLocal == True:
            self.searchNearFont(self.searchUpDir)
        self.searchExtensionsDirectory(self.extensionsDirectory)
        self.searchScriptsDirectory(self.scriptsDirectory)

    def searchNearFont(self, searchUpDirectories):
        fontDirectories = []
        if len(AllFonts()) > 0:
            for font in AllFonts():
                if font.path not in fontDirectories:
                    fontDirectories.append(font.path)
        s = self.scripts
        for fontDirectory in fontDirectories:
            fontDirectoryUp = "/".join(
                fontDirectory.split("/")[:-(searchUpDirectories)]
            )
            for dir, subdir, files in os.walk(fontDirectoryUp):
                for file in files:
                    if ".py" in file:
                        if ".pyc" not in file:
                            if file not in [ii[0] for ii in s]:
                                s[file] = (os.path.join(dir, file), "script")
                            else:
                                if s[file][0] != os.path.join(
                                    dir, file
                                ):  # avoid duplicate paths
                                    # add number to scripts with idential file names
                                    count = 1
                                    fileCount = "%s (%s).py" % (
                                        file.split(".")[0],
                                        count,
                                    )
                                    while fileCount in s:
                                        count += 1
                                        fileCount = "%s (%s).py" % (
                                            file.split(".")[0],
                                            count,
                                        )
                                    s[fileCount] = (os.path.join(dir, file), "script")

    def searchScriptsDirectory(self, scriptsDirectory):
        if not os.path.exists(scriptsDirectory):
            print("scripts folder not found: %s" % (scriptsDirectory))
        else:
            s = self.scripts
            for dir, subdir, files in os.walk(scriptsDirectory):
                for file in files:
                    if ".py" in file and not file.startswith("._"):
                        if ".pyc" not in file:
                            if file not in [ii[0] for ii in s]:
                                s[file] = (os.path.join(dir, file), "script")
                            else:
                                if s[file][0] != os.path.join(dir, file):
                                    # add number to scripts with idential file names
                                    count = 1
                                    fileCount = "%s (%s).py" % (
                                        file.split(".")[0],
                                        count,
                                    )
                                    while fileCount in s:
                                        count += 1
                                        fileCount = "%s (%s).py" % (
                                            file.split(".")[0],
                                            count,
                                        )
                                    s[fileCount] = (os.path.join(dir, file), "script")

    def searchExtensionsDirectory(self, extensionsDirectory):
        if not os.path.exists(extensionsDirectory):
            print("extensions folder not found: %s" % (extensionsDirectory))
        else:
            s = self.scripts
            for ext in os.listdir(extensionsDirectory):
                if ".roboFontExt" in ext:
                    if os.path.exists(
                        os.path.join(extensionsDirectory, ext, "info.plist")
                    ):
                        with open(
                            os.path.join(extensionsDirectory, ext, "info.plist"), "rb"
                        ) as f:
                            pl = plistlib.load(f)

                        if pl["launchAtStartUp"] == 0:  # not launched at startup
                            for i in pl["addToMenu"]:
                                extName = i["preferredName"]
                                extPath = i["path"]
                                extFullPath = os.path.join(
                                    extensionsDirectory, ext, "lib", extPath
                                )
                                if not os.path.exists(extFullPath):
                                    print(
                                        "%s missing path: %s" % (extName, extFullPath)
                                    )
                                else:
                                    s[extName] = (extFullPath, "ext")

    # # # # # # # # # # # # # #
    # Searching/Finding/Running
    # # # # # # # # # # # # # #

    def previousScript(self, sender):
        if len(self.w.list) > 1:
            if self.w.list.getSelection() == []:
                self.w.list.setSelection([0])
            else:
                i = self.w.list.getSelection()[0]
                if i > 0:
                    self.w.list.setSelection([i - 1])
                else:
                    self.w.list.setSelection([len(self.w.list.get()) - 1])

    def nextScript(self, sedner):
        if len(self.w.list) > 1:
            if self.w.list.getSelection() == []:
                self.w.list.setSelection([0])
            else:
                i = self.w.list.getSelection()[0]
                if i + 1 < len(self.w.list.get()):
                    self.w.list.setSelection([i + 1])
                else:
                    self.w.list.setSelection([0])

    def searchScripts(self, sender):
        i = sender.get()
        sub_list = []
        # pprint(self.scripts)

        # print("------------------")
        for k, ss in self.scripts.items():
            s, t = ss

            # r = fuzz.ratio(k, i)
            # # print(r, k, i)
            # if r > 40:
            #     sub_list.append((r,k,t))

            if i.lower().replace(" ", "") in k.lower().replace(" ", ""):
                sub_list.append((k, t))
            elif i.lower().replace(" ", "_") in k.lower().replace(" ", ""):
                sub_list.append((k, t))
            elif i.lower().replace(" ", "-") in k.lower().replace(" ", ""):
                sub_list.append((k, t))
            elif i.lower() in t:
                sub_list.append((k, t))

        # sub_list.sort(key=lambda x: x[0], reverse=True)
        sub_list = [{"name": i[0], "desc": i[1]} for i in sub_list]
        self.w.list.set(sub_list)
        self.w.list.setSelection([0])

    def executeScript(self, file, sender):
        try:
            runner(path=file)
        except Exception as e:
            print("Error. Script will not run. %s" % (e))
        self.lastScriptWrite(sender, file)

    def getKeyboardEquivalent(self, menu_item):
        ### frank
        key_equivalent = menu_item.keyEquivalent()
        modifier_mask = menu_item.keyEquivalentModifierMask()
        modifiers = []
        if modifier_mask & NSEventModifierFlagCommand:
            modifiers.append(MODIFIER_SYMBOLS["command"])
        if modifier_mask & NSEventModifierFlagShift:
            modifiers.append(MODIFIER_SYMBOLS["shift"])
        if modifier_mask & NSEventModifierFlagOption:
            modifiers.append(MODIFIER_SYMBOLS["option"])
        if modifier_mask & NSEventModifierFlagControl:
            modifiers.append(MODIFIER_SYMBOLS["control"])
        return f"{' + '.join(modifiers)} + {key_equivalent}" if key_equivalent else None

    def pullShortcuts(self):
        shorts = dict(getDefault("menuShortCuts", {}))
        shortcuts = []
        ### frank
        for (
            item,
            menu_item,
        ) in preferences.preferencesMenuShortCuts.getShortCuts().items():
            shortcut = self.getKeyboardEquivalent(menu_item)
            if shortcut:
                # print(item, "\t", shortcut)
                formatted = {"name": item, "desc": shortcut}
                shortcuts.append(formatted)
        self.w.list.set(shortcuts)

    def runScript(self, sender):
        if self.w.list.getSelection():
            value = self.w.list.get()[self.w.list.getSelection()[0]]
            # print(value)
            if value["name"] == "preferences":
                self.openPrefs(sender)
            elif value["name"] == "shortcuts":
                self.pullShortcuts()
            else:
                # print(value)
                if value["desc"] in ["script", "ext"]:
                    self.closeWindow(sender)
                    script_file = self.w.list.get()[self.w.list.getSelection()[0]][
                        "name"
                    ]
                    script_path = self.scripts[script_file][0]
                    if not os.path.exists(script_path):
                        print("script not found at path:", script_path)
                    else:
                        self.executeScript(script_path, sender)

    def openScriptInScriptingWindow(self, sender):
        if self.w.list.getSelection():
            if self.w.list.get()[self.w.list.getSelection()[0]]["name"] not in [
                "preferences",
                "shortcuts",
            ]:
                self.closeWindow(sender)
                script_file = self.w.list.get()[self.w.list.getSelection()[0]]["name"]
                script_path = self.scripts[script_file][0]
                if not os.path.exists(script_path):
                    print("script not found at path:", script_path)
                else:
                    if self.editor == "external":
                        subprocess.call(("open", script_path))
                    else:
                        OpenScriptWindow(script_path)

    def closeWindow(self, sender):
        self.w.close()


if __name__ == "__main__":
    Robocast()
