import re, time
import jinja2
from lxml import etree
from lxml.builder import E

from .facts import Facts

__all__ = ['xmlmode_netconf']

_NETCONF_EOM = ']]>]]>'
_xmlns = re.compile('xmlns=[^>]+')
_xmlns_strip = lambda text: _xmlns.sub('',text)
_junosns = re.compile('junos:')
_junosns_strip = lambda text: _junosns.sub('',text)

##### =========================================================================
##### xmlmode_netconf
##### =========================================================================

class tty_netconf(object):
  """
  Basic Junos XML API for bootstraping through the TTY
  """  

  def __init__(self, tty):
    self._tty = tty
    self.hello = None
    self.facts = Facts(self)

  ### -------------------------------------------------------------------------
  ### NECONF session open and close
  ### -------------------------------------------------------------------------

  def open(self, at_shell):
    """ start the XML API process and receive the 'hello' message """

    nc_cmd = ('junoscript' ,'xml-mode')[at_shell]
    self._tty.write( nc_cmd+' netconf need-trailer' )

    while True:
      time.sleep(0.1)
      line = self._tty._tty_dev_read()
      if line.startswith("<!--"): break

    self.hello = self._receive()

  def close(self, force=False):
    """ issue the XML API to close the session """

    # if we do not have an open connection, then return now.
    if force is False:
      if self.hello is None: return

    self._tty._tty_rawwrite('<rpc><close-session/></rpc>')
    self._tty._tty_flush()

  ### -------------------------------------------------------------------------
  ### Junos OS configuration methods
  ### -------------------------------------------------------------------------

  def load(self, content, **kvargs):
    """
    load-override a Junos 'conf'-style file into the device.  if the
    load is successful, return :True:, otherwise return the XML reply
    structure for further processing
    """
    action = kvargs.get('action','override')
    cmd = E('load-configuration', dict(format='text',action=action),
      E('configuration-text', content )
    )
    rsp = self.rpc(etree.tostring(cmd))
    return rsp if rsp.findtext('.//ok') is None else True

  def commit_check(self):
    """ 
    performs the Junos 'commit check' operation.  if successful return
    :True: otherwise return the response as XML for further processing.
    """
    rsp = self.rpc('<commit-configuration><check/></commit-configuration>')
    return True if 'ok' == rsp.tag else rsp

  def commit(self):
    """ 
    performs the Junos 'commit' operation.  if successful return
    :True: otherwise return the response as XML for further processing.
    """
    rsp = self.rpc('<commit-configuration/>')
    return True if 'ok' == rsp.tag else rsp

  def rollback(self):
    """ rollback that recent changes """
    cmd = E('load-configuration', dict(compare='rollback', rollback="0"))
    return self.rpc(etree.tostring(cmd))

  ### -------------------------------------------------------------------------
  ### XML RPC command execution
  ### -------------------------------------------------------------------------

  def rpc(self,cmd):
    """ 
    Write the XML cmd and return the response as XML object.

    :cmd: 
      <str> of the XML command.  if the :cmd: is not XML, then
      this routine will perform the brackets; i.e. if given
      'get-software-information', this routine will turn
      it into '<get-software-information/>'

    NOTES:
      The return XML object is the first child element after
      the <rpc-reply>.  There is also no error-checking
      performing by this routine.
    """
    if not cmd.startswith('<'): cmd = '<{}/>'.format(cmd)
    self._tty._tty_rawwrite('<rpc>{}</rpc>'.format(cmd))
    rsp = self._receive()    
    return rsp[0] # return first child after the <rpc-reply>

  ### -------------------------------------------------------------------------
  ### LOW-LEVEL I/O for reading back XML response
  ### -------------------------------------------------------------------------

  def _receive(self):
    """ process the XML response into an XML object """
    rxbuf = []
    while True:
      line = self._tty._tty_dev_read().strip()
      if not line: continue                       # if we got nothin, go again
      if _NETCONF_EOM == line: break              # check for end-of-message
      rxbuf.append(line)

    rxbuf[0] = _xmlns_strip(rxbuf[0])         # nuke the xmlns
    rxbuf[1] = _xmlns_strip(rxbuf[1])         # nuke the xmlns
    rxbuf = map(_junosns_strip, rxbuf)        # nuke junos: namespace

    return etree.XML(''.join(rxbuf))