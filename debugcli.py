#!/usr/bin/env python

from debugger import debughandler 
import bfdebug as bf
import traceback
import code
import textwrap
import re
import readline
import rlcompleter
import sys

if sys.version_info.major == 2:
  input = raw_input
else:
  input = input

# caching wrapper for tab-completion methods
def tabcomplete(fn):
  setattr(fn, "matches", [])
  def wrapped(text, state):
    if state == 0:
      fn.matches = fn(text)
    return fn.matches[state] if state < len(fn.matches) else None
  return wrapped

pg13 = True
languagename = "brainf***" if pg13 else "brainfuck"

def readline_gethist():
  print(readline.get_line_buffer())
  itemrange = range(1,readline.get_current_history_length()+1)
  histlist = [readline.get_history_item(x) for x in itemrange]
  return histlist

def readline_sethist(hist):
  readline.clear_history()
  for item in hist:
    readline.add_history(item)

# wrap a string, preserving indentation -- used for help messages
def messageformat(message):
    lines = textwrap.dedent(message).lstrip().splitlines()
    wrapper = textwrap.TextWrapper()
    def indent(line):
      wrapper.subsequent_indent = re.match("\s*", line).group()
      return wrapper.fill(line)
    lines = map(indent, lines)
    return "\n".join(lines)

# repl helper to make command-line methods available, including aliases
class debugdict:
  def __init__(self, debugcli):
    self.debugcli = debugcli
    self.commands = debugcli.commands
  def __getattr__(self, name):
    if name in self.commands:
      return self.commands[name]
    else:
      raise AttributeError
  def __dir__(self):
    return list(self.commands.keys())


class debugrepl(code.InteractiveConsole, object):
# with thanks to Abu Ashraf Masnum
# http://www.masnun.com/2014/01/09/embed-a-python-repl-in-your-program.html
  def __init__(self, *args, **kwargs):
    self.firstrun = True
    code.InteractiveConsole.__init__(self, *args, **kwargs)

  def interact(self):
    if self.firstrun:
      banner = messageformat("""
      Entering Python repl:
      Debugger commands are available from the 'cli' object, e.g. 'cli.run()'.
      The current debugger instance is available as 'debug'.
      The current {name} vm instance is available as 'vm'.
      Return to the debugger console with control-D.  Your variables will be preserved, so feel free to do this at any time.
      For everything else, please refer to the source or to your Python manual.

      Have fun!
      """.format(name=languagename)
      )
      self.firstrun = False
    else:
      banner = "Re-entering Python repl"
    code.InteractiveConsole.interact(self, banner)
    
  def raw_input(self, prompt=""):
    return input("repl>")
class debugcli:

  def __init__(self, scriptfile):
    self.debugger = debughandler(scriptfile)
    self.vm = self.debugger.vm
    self.initcommands()
    self.initrepl()
    self.clearlastcmd()
    self.colorize = True

  def initcommands(self):
    self.commands = {
      "mem": self.listmem,
      "list": self.listsource,
      "cmd": self.cmd,
      "run": self.run,
      "rrun": self.rrun,
      "addbrk": self.addbrk,
      "delbrk": self.delbrk,
      "quit": sys.exit,
      "input": self.setinput,
      "st": self.stacktrace,
      "": self.empty,
      "repl": self.dorepl,
      "help": self.gethelp,
      "color": self.setcolor,
      "alias": self.addalias,
      "addwatch": self.addwatch,
      "delwatch": self.delwatch,
      "watches": self.printAllWatches,
      "nextline": self.nextline,
      "prevline": self.prevline,
    }
    def addstepper(name):
# this can't be done in a loop, or each lambda will be bound to the same 'method' variable
      method = getattr(self.debugger, name)
      self.commands[name] = lambda *ignore: self._dostepper(method, True)
      self.commands["r"+name] = lambda *ignore: self._dostepper(method, False)
    for i in ["step","over","over2","out"]: addstepper(i)

  def cmd(self):
    print(self.vm.getcmd())

  def printcmd(self, *ignore):
    print(self.cmd())
    self.clearlastcmd()

  def parseoffset(self, initpos):
    offsetstr = initpos[0]
    if initpos[0] == '-':
      pos = self.vm.pos - int(initpos[1:])
    elif initpos[0] == '+':
      pos = self.vm.pos + int(initpos[1:])
    else:
      offsetstr = ''
      pos = int(initpos)
    return (offsetstr, pos)

  def listmem(self, widthstr = '10', rowsstr = '4', initpos = None, *ignore):
    vm = self.vm
    width = int(widthstr)
    rows = int(rowsstr)
    if initpos is None:
      pos = vm.pos - vm.pos % width
      offsetstr = ''
    else:
      offsetstr, pos = self.parseoffset(initpos)
    unfinished = bf.listmem(vm, width, rows, pos, self.debugger.watches.keys(), self.colorize)
    if unfinished:
      nextoffset = offsetstr + str(pos + width * rows)
      self.setlastcmd(self.listmem, widthstr, rowsstr, offsetstr + nextoffset)
    else:
      self.clearlastcmd()

  def listsource(self, linestr = None, linecountstr = '10', *ignore):
    line = None if linestr is None else int(linestr)
    linecount = int(linecountstr)
    linerange = bf.getlinerange(self.vm, line, linecount)
    self.listsourcerange(*linerange)

  def listsourcerange(self, startline, endline):
    unfinished = bf.bflist(self.vm, self.debugger.breaklines, (startline, endline), self.colorize)
    if unfinished and endline is not None:
      newrange = (endline, endline * 2 - (startline or 0))
      self.setlastcmd(self.listsourcerange, *newrange)
    else:
      self.clearlastcmd()

  def printWatch(self, pos, minsize = 0):
    formatstr = "{{: <{}}}  {{:04d}}  ".format(minsize)
    vm = self.vm
    statepos = self.vm.statepos
    if vm.pos == pos and vm.fwdstate and vm.fwdstate[statepos-1].value is not None:
      valuestr = "{:02x} -> {:02x}".format(
          vm.backstate[statepos-1].value,
          vm.fwdstate[statepos-1].value
      )
    else:
      valuestr = "{}".format(vm.state[vm.pos])
    namestr = formatstr.format(self.debugger.watches[pos], pos)
    print(namestr + valuestr)

  def printAllWatches(self, *ignore):
    if len(self.debugger.watches) == 0:
      print("No watches")
    else:
      minsize = max([len(x) for x in self.debugger.watches.values()])
      for key in sorted(self.debugger.watches.keys()):
        self.printWatch(key, minsize)

  def _dostepper(self, stepper, forward):
    self.setlastcmd(self._dostepper, stepper, forward)
    if stepper(forward):
      return self.cmd()
    else:
      print("done!")

  def run(self, *ignore):
    self._dostepper(self.debugger.run, True)
    self.after_run()
  def rrun(self, *ignore):
    self._dostepper(self.debugger.run, False)
    self.after_run()

  def after_run(self):
    if self.debugger.isBreakpoint():
      print("reached breakpoint at line {}".format(self.vm.getcmd().pos.line))
    if self.debugger.isWatchpoint():
      print("reached watchpoint at memory position {}".format(self.vm.pos))
      self.printWatch(self.vm.pos)

  def nextline(self, *ignore):
    self._dostepper(self.debugger.nextline, True)
  def prevline(self, *ignore):
    self._dostepper(self.debugger.nextline, False)

  def stacktrace(self, *ignore):
    for i, l in enumerate(self.debugger.loopstack):
      print("{: 2d}  {}".format(i, l))
    self.clearlastcmd()

  def addbrk(self, linestr, *ignore):
    ok, errmsg = self.debugger.addbrk(int(linestr))
    if not ok: print(errmsg)
    self.clearlastcmd()

  def delbrk(self, linestr, *ignore):
    ok, errmsg = self.debugger.delbrk(int(linestr))
    if not ok: print(errmsg)
    self.clearlastcmd()

  def addwatch(self, name, pos=None, *ignore):
    if pos is None:
      pos = self.vm.pos
    else:
      pos = self.parseoffset(pos)[1]
    ok, errmsg = self.debugger.addwatch(name, pos)
    if not ok: print(errmsg)

  def delwatch(self, namepos, *ignore):
    try:
      pos = self.parseoffset(namepos)[1]
      ok, msg = self.debugger.delwatchbypos(pos)
    except ValueError:
      ok, msg = self.debugger.delwatchbyname(namepos)
    print(msg)

  def addalias(self, name, target, *args):
    def alias(*moreargs):
      newargs = args + moreargs
      self.commands[target](*newargs)
    self.commands[name] = alias

  def setcolor(self, color=None, *ignore):
    if color is None:
      print("color is " + ("on" if self.colorize is True else "off"))
    else:
      self.colorize = color.lower() in ["on", "true", "1", "yes"]

  def initrepl(self):
    mylocals = locals()
    commands = debugdict(self)
    mylocals["cli"] = commands
    mylocals["debug"] = self.debugger
    mylocals["vm"] = self.vm
    self.repl = debugrepl(mylocals)
    self.replhist = []
    self.replcompleter = rlcompleter.Completer(mylocals).complete

  def dorepl(self, *ignore):
    cmdhist = readline_gethist()
    completer = readline.get_completer()
    readline_sethist(self.replhist)
    readline.set_completer(self.replcompleter)

    self.repl.interact()

    self.replhist = readline_gethist()
    readline.set_completer(completer)
    readline_sethist(cmdhist)

    self.clearlastcmd()

  def noop(self, *ignore): pass

  def empty(self, *ignore):
    self.lastcmd(*self.lastargs)

  def setinput(self, filename, *ignore):
    self.debugger.setinput(filename)
    self.clearlastcmd()


  def gethelp(self, *ignore):
    lines = messageformat("""
    {name} debugger console

    Available commands:
      mem [width] [rows] [[+|-]position]
        Display the contents of memory as 'rows' rows of 'width' bytes.  If + or - is supplied, position is specified as an offset from the vm's current position, otherwise it is an absolute address.
      list [line] [linecount]
        Display 'linecount' lines from the source, centered on 'line'.  'line' defaults to the current instruction.  Color highlighting is supplied regardless of whether it is supported.  Lines with breakpoints are marked with a *.
      cmd
        Display the next command to be run.
      step
        Execute a single command.  Note that runs of increments/decrements and pointer moves are treated as single commands.
      rstep
        Undo a single command, moving backwards through the program's execution.
      st
        Show a "stack trace" of the loops the vm is currently inside.
      out
        Return from a loop.
      over
        Step over the next instruction, stopping at completion of a single pass through a loop.
      over2
        Step over the next instruction, stopping at completion of all passes through a loop.
      nextline
        Execute code until the next line.
      run
        Continue executing until a breakpoint or the end of the program.  Note that run and rrun are currently the only commands to take note of breakpoints and watchpoints.
      rover, rover2, prevline, rout, rrun:
        All perform the same action as their similarly-named counterparts, but in reverse.
      addbrk line
        Set a breakpoint on 'line'.
      delbrk line
        Remove the breakpoint from 'line'.
      input filename
        Provide input to the vm from the given file, rather than stdin.
      alias command [args]
        Add an alias for a command.  It will be executed with the commands provided to the alias as well as any you subsequently provide.
      addwatch name [pos]
        Watch a memory location and break on changes.  Defaults to the pointer's current address.
      delwatch name|pos
        Remove a watch.
      watches
        List all watches and their current values.
      repl
        Enter a Python repl.
      color on|off
        Switch commands from colorized (default) to uncolored output.
      help
        Display this help.
      quit
        Exit the debugger.""".format(name=languagename.title()))
    print(lines)
    self.clearlastcmd()


  def clearlastcmd(self):
    self.setlastcmd(self.noop)

  def setlastcmd(self, cmd, *args):
    self.lastcmd = cmd
    self.lastargs = args

def handle(debug, input):
  split = input.split(" ")
  commandname = split[0]
  if commandname not in debug.commands:
    print("I don't recognize '{}'!\nTry 'help' for a list of all supported commands.".format(commandname))
  else:
    command = debug.commands[commandname]
    args = split[1:]
    try:
      result = command(*args)
      if result is not None:
        print(result)
    except Exception as e:
      print("error processing command:")
      traceback.print_exc()

def getcompleter(cli):
  @tabcomplete
  def clicompleter(text):
    return list(filter(lambda a: a.startswith(text), cli.commands.keys()))
  return clicompleter

def main():
  rccmds = []
  try:
    with open(".bfrc") as rcfile:
      rccmds = rcfile.read().splitlines()
  except IOError: pass
  with open(sys.argv[1]) as infile:
    debug = debugcli(infile.read())
  for cmd in rccmds:
    handle(debug, cmd)
  readline.set_completer(getcompleter(debug))
  readline.parse_and_bind("tab: complete")
  while True:
    try:
      command = input("> ")
    except EOFError: sys.exit()
    except KeyboardInterrupt: sys.exit()
    else:
      handle(debug, command)

if __name__ == "__main__":
  main()

