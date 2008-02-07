""" ReplicationPlacementHandler is the service interface to the ReplicationPlacementDB.
"""

from types import *
from DIRAC.Core.DISET.RequestHandler import RequestHandler
from DIRAC import gLogger, gMonitor, gConfig, S_OK, S_ERROR
from DIRAC.DataManagementSystem.DB.ReplicationPlacementDB import ReplicationPlacementDB
from DIRAC.Core.Transformation.TransformationHandler import TransformationHandler

# This is a global instance of the ReplicationPlacementDB class
placementDB = False

def initializeReplicationPlacementHandler(serviceInfo):
  global placementDB
  placementDB = ReplicationPlacementDB()
  return S_OK()

class ReplicationPlacementHandler(TransformationHandler):

  def __init__(self,*args,**kargs):

    self.setDatabase(placementDB)
    TransformationHandler.__init__(self,*args,**kargs)

  types_publishTransformation = []
  def export_publishTransformation(self, transName, desciption,longDesription, type, mode, fileMask):
    """ Publish new transformation in the TransformationDB
    """
    authorDN = self.transport.peerCredentials['DN']
    #authorName = self.transport.peerCredentials['user']
    authorGroup = self.transport.peerCredentials['group']
    try:
      res = placementDB.addTransformation(transName,desciption,longDesription,authorDN,authorGroup,type,mode,'ReplicationPlacementAgent','New',fileMask)
      return res
    except Exception,x:
      errStr = "ReplicationPlacementHandler.publishTransformation: Exception while adding transformation."
      gLogger.exception(errStr,str(x))
      return S_ERROR(errStr)


