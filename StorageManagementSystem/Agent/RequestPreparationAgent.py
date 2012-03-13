# $HeadURL$

__RCSID__ = "$Id$"

from DIRAC import gLogger, gConfig, gMonitor, S_OK, S_ERROR, rootPath

from DIRAC.Core.Base.AgentModule                                import AgentModule
from DIRAC.StorageManagementSystem.Client.StorageManagerClient  import StorageManagerClient
from DIRAC.Resources.Catalog.FileCatalog                        import FileCatalog
from DIRAC.DataManagementSystem.Client.DataIntegrityClient      import DataIntegrityClient
from DIRAC.StorageManagementSystem.DB.StorageManagementDB       import StorageManagementDB

import time, os, sys, re
from types import *
#test 1
AGENT_NAME = 'StorageManagement/RequestPreparationAgent'

class RequestPreparationAgent( AgentModule ):

  def initialize( self ):
    self.fileCatalog = FileCatalog()
    #self.stagerClient = StorageManagerClient()
    self.dataIntegrityClient = DataIntegrityClient()
    self.storageDB = StorageManagementDB()
    # This sets the Default Proxy to used as that defined under
    # /Operations/Shifter/DataManager
    # the shifterProxy option in the Configuration can be used to change this default.
    self.am_setOption( 'shifterProxy', 'DataManager' )

    return S_OK()

  def execute( self ):
    res = self.prepareNewReplicas()
    return res

  def prepareNewReplicas( self ):
    """ This is the first logical task to be executed and manages the New->Waiting transition of the Replicas
    """
    res = self.__getNewReplicas()
    if not res['OK']:
      gLogger.fatal( "RequestPreparation.prepareNewReplicas: Failed to get replicas from StagerDB.", res['Message'] )
      return res
    if not res['Value']:
      gLogger.info( "There were no New replicas found" )
      return res
    replicas = res['Value']['Replicas']
    replicaIDs = res['Value']['ReplicaIDs']
    gLogger.info( "RequestPreparation.prepareNewReplicas: Obtained %s New replicas for preparation." % len( replicaIDs ) )

    # Check that the files exist in the FileCatalog
    res = self.__getExistingFiles( replicas.keys() )
    if not res['OK']:
      return res
    exist = res['Value']['Exist']
    terminal = res['Value']['Missing']
    failed = res['Value']['Failed']
    if not exist:
      gLogger.error( 'RequestPreparation.prepareNewReplicas: Failed determine existance of any files' )
      return S_OK()
    terminalReplicaIDs = {}
    for lfn, reason in terminal.items():
      for se, replicaID in replicas[lfn].items():
        terminalReplicaIDs[replicaID] = reason
      replicas.pop( lfn )
    gLogger.info( "RequestPreparation.prepareNewReplicas: %s files exist in the FileCatalog." % len( exist ) )
    if terminal:
      gLogger.info( "RequestPreparation.prepareNewReplicas: %s files do not exist in the FileCatalog." % len( terminal ) )

    # Obtain the file sizes from the FileCatalog
    res = self.__getFileSize( exist )
    if not res['OK']:
      return res
    failed.update( res['Value']['Failed'] )
    terminal = res['Value']['ZeroSize']
    fileSizes = res['Value']['FileSizes']
    if not fileSizes:
      gLogger.error( 'RequestPreparation.prepareNewReplicas: Failed determine sizes of any files' )
      return S_OK()
    for lfn, reason in terminal.items():
      for se, replicaID in replicas[lfn].items():
        terminalReplicaIDs[replicaID] = reason
      replicas.pop( lfn )
    gLogger.info( "RequestPreparation.prepareNewReplicas: Obtained %s file sizes from the FileCatalog." % len( fileSizes ) )
    if terminal:
      gLogger.info( "RequestPreparation.prepareNewReplicas: %s files registered with zero size in the FileCatalog." % len( terminal ) )

    # Obtain the replicas from the FileCatalog
    res = self.__getFileReplicas( fileSizes.keys() )
    if not res['OK']:
      return res
    failed.update( res['Value']['Failed'] )
    terminal = res['Value']['ZeroReplicas']
    fileReplicas = res['Value']['Replicas']
    if not fileReplicas:
      gLogger.error( 'RequestPreparation.prepareNewReplicas: Failed determine replicas for any files' )
      return S_OK()
    for lfn, reason in terminal.items():
      for se, replicaID in replicas[lfn].items():
        terminalReplicaIDs[replicaID] = reason
      replicas.pop( lfn )
    gLogger.info( "RequestPreparation.prepareNewReplicas: Obtained replica information for %s file from the FileCatalog." % len( fileReplicas ) )
    if terminal:
      gLogger.info( "RequestPreparation.prepareNewReplicas: %s files registered with zero replicas in the FileCatalog." % len( terminal ) )

    # Check the replicas exist at the requested site
    replicaMetadata = []
    for lfn, requestedSEs in replicas.items():
      lfnReplicas = fileReplicas[lfn]
      for requestedSE, replicaID in requestedSEs.items():
        if not requestedSE in lfnReplicas.keys():
          terminalReplicaIDs[replicaID] = "LFN not registered at requested SE"
          replicas[lfn].pop( requestedSE )
        else:
          replicaMetadata.append( ( replicaID, lfnReplicas[requestedSE], fileSizes[lfn] ) )

    # Update the states of the files in the database
    if terminalReplicaIDs:
      gLogger.info( "RequestPreparation.prepareNewReplicas: %s replicas are terminally failed." % len( terminalReplicaIDs ) )
      #res = self.stagerClient.updateReplicaFailure( terminalReplicaIDs )
      res = self.storageDB.updateReplicaFailure( terminalReplicaIDs )
      if not res['OK']:
        gLogger.error( "RequestPreparation.prepareNewReplicas: Failed to update replica failures.", res['Message'] )
    if replicaMetadata:
      gLogger.info( "RequestPreparation.prepareNewReplicas: %s replica metadata to be updated." % len( replicaMetadata ) )
      # Sets the Status='Waiting' of CacheReplicas records that are OK with catalogue checks
      res = self.storageDB.updateReplicaInformation( replicaMetadata )
      if not res['OK']:
        gLogger.error( "RequestPreparation.prepareNewReplicas: Failed to update replica metadata.", res['Message'] )
    return S_OK()

  def __getNewReplicas( self ):
    """ This obtains the New replicas from the Replicas table and for each LFN the requested storage element """
    # First obtain the New replicas from the CacheReplicas table
    res = self.storageDB.getCacheReplicas( {'Status':'New'} )
    if not res['OK']:
      gLogger.error( "RequestPreparation.__getNewReplicas: Failed to get replicas with New status.", res['Message'] )
      return res
    if not res['Value']:
      gLogger.debug( "RequestPreparation.__getNewReplicas: No New replicas found to process." )
      return S_OK()
    else:
      gLogger.debug( "RequestPreparation.__getNewReplicas: Obtained %s New replicas(s) to process." % len( res['Value'] ) )
    replicas = {}
    replicaIDs = {}
    for replicaID, info in res['Value'].items():
      lfn = info['LFN']
      storageElement = info['SE']
      if not replicas.has_key( lfn ):
        replicas[lfn] = {}
      replicas[lfn][storageElement] = replicaID
      replicaIDs[replicaID] = ( lfn, storageElement )
    return S_OK( {'Replicas':replicas, 'ReplicaIDs':replicaIDs} )

  def __getExistingFiles( self, lfns ):
    """ This checks that the files exist in the FileCatalog. """
    filesExist = []
    missing = {}
    res = self.fileCatalog.exists( lfns )
    if not res['OK']:
      gLogger.error( "RequestPreparation.__getExistingFiles: Failed to determine whether files exist.", res['Message'] )
      return res
    failed = res['Value']['Failed']
    for lfn, exists in res['Value']['Successful'].items():
      if exists:
        filesExist.append( lfn )
      else:
        missing[lfn] = 'LFN not registered in the FileCatalog'
    if missing:
      for lfn, reason in missing.items():
        gLogger.warn( "RequestPreparation.__getExistingFiles: %s" % reason, lfn )
      self.__reportProblematicFiles( missing.keys(), 'LFN-LFC-DoesntExist' )
    return S_OK( {'Exist':filesExist, 'Missing':missing, 'Failed':failed} )

  def __getFileSize( self, lfns ):
    """ This obtains the file size from the FileCatalog. """
    failed = []
    fileSizes = {}
    zeroSize = {}
    res = self.fileCatalog.getFileSize( lfns )
    if not res['OK']:
      gLogger.error( "RequestPreparation.__getFileSize: Failed to get sizes for files.", res['Message'] )
      return res
    failed = res['Value']['Failed']
    for lfn, size in res['Value']['Successful'].items():
      if size == 0:
        zeroSize[lfn] = "LFN registered with zero size in the FileCatalog"
      else:
        fileSizes[lfn] = size
    if zeroSize:
      for lfn, reason in zeroSize.items():
        gLogger.warn( "RequestPreparation.__getFileSize: %s" % reason, lfn )
      self.__reportProblematicFiles( zeroSize.keys(), 'LFN-LFC-ZeroSize' )
    return S_OK( {'FileSizes':fileSizes, 'ZeroSize':zeroSize, 'Failed':failed} )

  def __getFileReplicas( self, lfns ):
    """ This obtains the replicas from the FileCatalog. """
    replicas = {}
    noReplicas = {}
    res = self.fileCatalog.getReplicas( lfns )
    if not res['OK']:
      gLogger.error( "RequestPreparation.__getFileReplicas: Failed to obtain file replicas.", res['Message'] )
      return res
    failed = res['Value']['Failed']
    for lfn, lfnReplicas in res['Value']['Successful'].items():
      if len( lfnReplicas.keys() ) == 0:
        noReplicas[lfn] = "LFN registered with zero replicas in the FileCatalog"
      else:
        replicas[lfn] = lfnReplicas
    if noReplicas:
      for lfn, reason in noReplicas.items():
        gLogger.warn( "RequestPreparation.__getFileReplicas: %s" % reason, lfn )
      self.__reportProblematicFiles( noReplicas.keys(), 'LFN-LFC-NoReplicas' )
    return S_OK( {'Replicas':replicas, 'ZeroReplicas':noReplicas, 'Failed':failed} )

  def __reportProblematicFiles( self, lfns, reason ):
    return S_OK()
    res = self.dataIntegrityClient.setFileProblematic( lfns, reason, self.name )
    if not res['OK']:
      gLogger.error( "RequestPreparation.__reportProblematicFiles: Failed to report missing files.", res['Message'] )
      return res
    if res['Value']['Successful']:
      gLogger.info( "RequestPreparation.__reportProblematicFiles: Successfully reported %s missing files." % len( res['Value']['Successful'] ) )
    if res['Value']['Failed']:
      gLogger.info( "RequestPreparation.__reportProblematicFiles: Failed to report %s problematic files." % len( res['Value']['Failed'] ) )
    return res
