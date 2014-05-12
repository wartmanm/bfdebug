import sys
# base class for the eight bf instructions
class bfcommand:
  def __init__(self, pos, parent):
    self.pos = pos
    self.nextcmd = None
    self.parent = parent
  def setnext(self, nextcmd):
    self.nextcmd = nextcmd
  def getnext(self, state, pos):
    return self.nextcmd
  def run(self, state, pos, instream, outstream):
    return bflog(self, None, None)
  def __repr__(self): return "noop"

# record of a single state transition
class bflog:
  def __init__(self, cmd, value, pos):
    self.cmd = cmd
    self.value = value
    self.pos = pos
  def __repr__(self):
    return "(value: {}, state: {})".format(repr(self.value), repr(self.pos))

# position of a bf instruction in the input
class bfpos:
  def __init__(self, line, start, end=None):
    self.start = start
    self.end = start + 1 if end is None else end
    self.line = line

class bfread(bfcommand):
  def run(self, state, pos, instream, outstream):
    inchar = ord(instream.read(1))
    return bflog(self, inchar, None)
  def __repr__(self): return ","

class bfwrite(bfcommand):
  def run(self, state, pos, instream, outstream):
    print("char is %s: %s" % (state[pos], chr(state[pos])))
    outstream.write(chr(state[pos]))
    return bflog(self, None, None)
  def __repr__(self): return "."

class bfmover(bfcommand):
  def __init__(self, pos, parent, amount):
    bfcommand.__init__(self, pos, parent)
    self.amount = amount
  def run(self, state, pos, instream, outstream):
    return bflog(self, None, pos+self.amount)
  def __repr__(self):
    if self.amount == 0: return ""
    char = "<" if self.amount < 0 else ">"
    if abs(self.amount) == 1: return char
    return char + str(abs(self.amount))

class bfadder(bfcommand):
  def __init__(self, pos, parent, amount):
    bfcommand.__init__(self, pos, parent)
    self.amount = amount
  def run(self, state, pos, instream, outstream):
    return bflog(self, state[pos]+self.amount, None)
  def __repr__(self):
    return "{:+d}".format(self.amount)

class bfcond(bfcommand):
  def getnext(self, state, pos):
    return self.subcmds[0] if state[pos] else self.nextcmd
  def setsubcmds(self, subcmds):
    self.subcmds = subcmds
  def __repr__(self):
    lines = map(repr, self.subcmds)
    return "[ " + " ".join(lines) + " ]"

def parse(script, pos, line, outercmd):
  cmds = []
  while pos < len(script):
    bfchar = script[pos];
    cmd = None
    if bfchar == '.':
      cmd = bfwrite(bfpos(line, pos), outercmd)
    elif bfchar == ',':
      cmd = bfread(bfpos(line, pos), outercmd)
    elif bfchar in '-+':
      startpos = pos
      amount = 0
      while bfchar in '-+':
        if bfchar == '+':
          amount += 1
        else:
          amount -= 1
        pos += 1
        bfchar = script[pos]
      cmd = bfadder(bfpos(line, startpos, pos), outercmd, amount)
      pos -= 1
    elif bfchar in '<>':
      startpos = pos
      offset = 0
      while bfchar in '<>':
        if bfchar == '<':
          offset -= 1
        else:
          offset += 1
        pos += 1
        bfchar = script[pos]
      cmd = bfmover(bfpos(line, startpos, pos), outercmd, offset)
      pos -= 1
    elif bfchar == '[':
      cmd = bfcond(bfpos(line, pos), outercmd)
      subcmds, nextpos, nextline = parse(script, pos+1, line, cmd)
      cmd.setsubcmds(subcmds)
      pos = nextpos
      line = nextline
    elif bfchar == ']':
      cmd = bfcommand(bfpos(line, pos), outercmd)
      break
    elif bfchar in ';#' or (bfchar == '/' and script[pos+1] == '/'):
      while(script[pos] != '\n'):
        pos += 1
      pos -= 1
    elif bfchar == '\n':
      line += 1
    if cmd:
      cmds.append(cmd)
    if len(cmds) > 1:
      cmds[-2].setnext(cmds[-1])
    pos += 1
  cmds[-1].setnext(outercmd)
  return (cmds, pos, line)

def runcmd(cmd, state, pos, instream, outstream):
  new = cmd.run(state, pos, instream, outstream)
  oldpos = None
  if new.pos is not None:
    oldpos = pos
    pos = new.pos
  oldvalue = None
  if new.value is not None:
    oldvalue = state[pos]
  log = bflog(None, oldvalue, oldpos)
  return (log, new)

# simple VM which can build a list of state transitions using stepend()
# and move foward and backwards through them using step() and rstep()
# this is a very memory-intensive way to implement reversibility, as the
# only operations which are not inherently reversible and need to be
# recorded are loops and reading input - the rest can be safely ignored.
# however, it is very, very simple
class bfrunner:
  def __init__(self, script, instream=sys.stdin, outstream=sys.stdout):
    initcmd = bfcommand(bfpos(0, 0, 0), None)
    endpos = bfpos(script.count("\n"), len(script), len(script))
    endcmd = bfcommand(endpos, None)
    initcmd.parent = endcmd
    self.allcmds = parse(script, 0, 0, None)[0]
    initcmd.setnext(self.allcmds[0])
    self.allcmds[-1].setnext(endcmd)
    self.initcmd = initcmd
    self.newcmd = initcmd
    self.endcmd = endcmd
    self.statelen = 0
    self.statepos = 0
    self.backstate = []
    self.fwdstate = []
    self.state = [0 for x in range(16384)]
    self.pos = 0
    self.script = script
    self.instream = instream
    self.outstream = outstream
  def resetfuture(self, fwdlen = 0):
# won't reset position in input streams, so be careful
    if fwdlen < 0:
      raise ValueError
    length = self.statepos + fwdlen
    if length >= self.statelen:
      return
    if length > self.statepos:
      cmd = self.fwdstate[length].cmd
    else:
      cmd = self.getcmd()
    self.statelen = length
    self.backstate = self.backstate[:length]
    self.fwdstate = self.fwdstate[:length]
    self.newcmd = cmd
  def resetpast(self, backlen = 0):
    if backlen < 0:
      raise ValueError
    start = max(self.statepos - backlen, 0)
    self.statelen = self.statelen - start
    self.statepos = self.statepos - start
    self.fwdstate = self.fwdstate[start:]
    self.backstate = self.backstate[start:]

  def stepend(self):
    if self.newcmd is self.endcmd:
      raise StopIteration
    else:
      oldstate, newstate = runcmd(self.newcmd, self.state, self.pos, self.instream, self.outstream)
      self.backstate.append(oldstate)
      self.fwdstate.append(newstate)
      self.applystate(newstate)
      self.newcmd = self.newcmd.getnext(self.state, self.pos)
      self.statelen += 1
      self.statepos += 1
  def step(self):
    oldcmd = self.getcmd()
    if self.statepos >= self.statelen:
      self.stepend()
    else:
      self.applystate(self.fwdstate[self.statepos])
      self.statepos += 1
    return oldcmd
  def rstep(self):
    if (self.statepos > 0):
      state = self.backstate[self.statepos-1]
    else:
      raise StopIteration
    self.applystate(state)
    self.statepos -= 1
  def applystate(self, newstate):
    if newstate.pos is not None: self.pos = newstate.pos
    if newstate.value is not None: self.state[self.pos] = newstate.value
  def getcmd(self):
    if self.statepos >= self.statelen:
      return self.newcmd
    return self.fwdstate[self.statepos].cmd

def scriptformat(vm):
  return " ".join(map(str, vm.allcmds))

def linegen(s):
  pos = 0
  yield pos
  while True:
    pos = s.find("\n", pos)
    if pos == -1: break
    yield pos + 1 # first char after newline
    pos += 1

def getlinerange(vm, center = None, linecount=10):
  linemax = vm.script.count("\n")+1
  pos = vm.getcmd().pos
  centerline = pos.line if center is None else center
  startline = centerline - int(linecount/2)
  endline = centerline + int(linecount/2)
  if startline < 0:
    endline += 0 - startline
    startline = 0
  if endline > linemax:
    startline -= endline - linemax
    endline = linemax
  if startline < 0:
    startline = 0
  if startline == 0: startline = None
  if endline == linemax: endline = None
  return (startline, endline)

def bflist(vm, brklist, linerange, color=True):
  lines = vm.script.splitlines(True)
  pos = vm.getcmd().pos
  startline, endline = linerange
  startline = startline or 0
  if endline is None or endline > len(lines):
    endline = len(lines)
  if startline >= len(lines):
    return False

  charidx = list(linegen(vm.script))[startline]
  for index in range(startline, endline):
    line = lines[index]
    cmdstart = pos.start - charidx
    cmdend = pos.end - charidx
    brkmark = "*" if index in brklist else " "
    if color:
      init = "{}{: 3d} ".format(brkmark, index)
    else:
      linemark = "@" if 0 <= cmdstart < len(line) and not color else " "
      init = "{}{: 3d} {} ".format(brkmark, index, linemark)
    sys.stdout.write(init)
    if cmdstart < 0 and cmdend > 0:
      cmdstart = 0
    if cmdstart >= 0 and cmdstart < len(line):
      if color:
        sys.stdout.write(line[:cmdstart])
        sys.stdout.write("\x1B[31m")
        sys.stdout.write(line[cmdstart:cmdend])
        sys.stdout.write("\x1B[0m")
        sys.stdout.write(line[cmdend:])
      else:
        sys.stdout.write(line)
        sys.stdout.write(" " * (cmdstart + len(init)))
        sys.stdout.write("^" * (cmdend - cmdstart))
        sys.stdout.write("\n")
    else:
      sys.stdout.write(line)
    charidx += len(line)
  return endline < len(lines)

def listmem(vm, width, rows, pos, watches, color = True):
  fmt = "{:02x} "
  curpos = pos
  ptrrow = int((vm.pos - pos) / width)
  ptroffset = (vm.pos - pos) % width
  rowcount = 0
  rowpos = 0
  maxrow = int((len(vm.state) - pos) / width + 1)
  truerows = min(rows, maxrow)
  for rowcount in range(truerows):
    indexformatted = "{: 4d}: ".format(curpos)
    sys.stdout.write(indexformatted)
    printextra = False
    extrastrs = [None for x in range(width)]
    for rowpos in range(width):
      if (curpos < len(vm.state)):
        formatted = fmt.format(vm.state[curpos])
      else:
        formatted = "  "
      if color:
        newcolor = None
        if curpos == vm.pos:
          if curpos in watches: newcolor = "5"
          else: newcolor = "1"
        elif curpos in watches: newcolor = "6"
        if newcolor:
          sys.stdout.write("\x1B[3" + newcolor +"m")
          sys.stdout.write(formatted)
          sys.stdout.write("\x1B[0m")
        else:
          sys.stdout.write(formatted)
      else:
        extrastr = None
        if curpos == vm.pos:
          printextra = True
          if curpos in watches: extrastr = "!!"
          else: extrastr = "^^"
        elif curpos in watches: extrastr = "##"
        extrastrs[rowpos] = extrastr
        if extrastr:
          printextra = True
        sys.stdout.write(formatted)
      curpos += 1
    sys.stdout.write("\n")
    if not color and printextra:
      sys.stdout.write(" "*len(indexformatted))
      for entry in extrastrs:
        sys.stdout.write(entry if entry is not None else "  ")
        sys.stdout.write(" ")
      sys.stdout.write("\n")
  return pos + 1 < len(vm.state)
