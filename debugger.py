import bfdebug as bf


class debughandler:
  def __init__(self, scriptfile):
    self.oldlinepos = 0
    self.linepos = 0
    self.breaklines = set()
    self.watches = {}
    self.vm = bf.bfrunner(scriptfile)
    self.loopstack = []

  def isBreakpoint(self):
    if (self.oldlinepos != self.linepos):
      if (self.linepos in self.breaklines):
        return True
    return False
  
  def isWatchpoint(self):
# Only memory at the current pointer location can be modified, so this is pretty straightforward.
# If you're porting this to run, I don't know, Mindfuck 2.0, you probably want to do something else here.
    if self.vm.pos in self.watches and self.vm.fwdstate and self.vm.fwdstate[self.vm.statepos-1].value is not None:
      return True
    return False

  def addbrk(self, line):
    if (line in self.breaklines):
      return False, "already breaking on line {}!".format(line)
    else:
      self.breaklines.add(line)
      return True, None

  def delbrk(self, line):
    if (line not in self.breaklines):
      return False, "line {} not a breakpoint!".format(line)
    else:
      self.breaklines.discard(line)
      return True, None

  def addwatch(self, name, pos):
    if pos in self.watches:
      return False, "A watch at position {} is already present as '{}'".format(pos, watches[pos])
    else:
      self.watches[pos] = name
      return True, None

  def delwatchbypos(self, pos):
    if pos in self.watches:
      name = self.watches.pop(pos)
      return True, "removed " + name
    else:
      return False, "no watch found at position {}".format(namepos)

  def delwatchbyname(self, name):
    for k,v in self.watches.items():
      if v == namepos:
        return self.delwatchbypos(k)
    return False, "no watch found named '{}'".format(namepos)

  def _dostep(self):
    self.oldlinepos = self.linepos
    self.linepos = self.vm.getcmd().pos.line

    cmd = self.vm.getcmd()
    head = self.loopstack[-1] if len(self.loopstack) > 0 else None
    if cmd == head:
      self.loopstack.pop()
    elif cmd.parent != head and cmd.parent != None:
      self.loopstack.append(cmd.parent)

  def safe_step(self):
    try:
      self.vm.step()
      self._dostep()
      return True
    except StopIteration:
      return False

  def safe_rstep(self):
    try:
      self.vm.rstep()
      self._dostep()
      return True
    except StopIteration:
      return False

  def _choosestepper(self, forward):
    return self.safe_step if forward else self.safe_rstep

  def step(self, forward = True):
    return self.safe_step() if forward else self.safe_rstep()
  def run(self, forward = True):
    return self._runsteps(self._choosestepper(forward))
  def over(self, forward = True):
    return self._runover(self._choosestepper(forward))
  def over(self, forward = True):
    return self._runover(self._choosestepper(forward))
  def over2(self, forward = True):
    return self._runover2(self._choosestepper(forward))
  def out(self, forward = True):
    return self._runout(self._choosestepper(forward))
  def nextline(self, forward = True):
    return self._runnextline(self._choosestepper(forward))
  
  def _runsteps(self, stepper):
    unfinished = True
    while True:
      unfinished = stepper()
      if not unfinished or self.isBreakpoint() or self.isWatchpoint():
        return unfinished

  def _runout(self, stepper):
    depth = len(self.loopstack)
    cmd = self.vm.getcmd().parent
    if not self.loopstack:
      print("not currently in a loop")
      return True
    while True:
      unfinished = stepper()
      if not unfinished or (len(self.loopstack) < depth and cmd != self.vm.getcmd()):
        return unfinished

  def _runover(self, stepper):
    depth = len(self.loopstack)
    while True:
      unfinished = stepper()
      if not unfinished or len(self.loopstack) <= depth:
        return unfinished

  def _runover2(self, stepper):
    depth = len(self.loopstack)
    cmd = self.vm.getcmd()
    while True:
      unfinished = self._runover(stepper)
      if not unfinished or cmd != self.vm.getcmd():
        return unfinished

  def _runnextline(self, stepper):
    curline = self.linepos
    while True:
      unfinished = stepper()
      if not unfinished or self.linepos != curline:
        return unfinished
  
  def setinput(self, filename):
    self.vm.instream = open(filename, "rb")

