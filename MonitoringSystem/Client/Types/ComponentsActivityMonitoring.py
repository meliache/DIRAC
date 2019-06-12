"""
ComponentsActivityMonitoring type is used to monitor activity of DIRAC components.
"""

from DIRAC.MonitoringSystem.Client.Types.BaseType import BaseType

__RCSID__ = "$Id$"

########################################################################


class ComponentsActivityMonitoring(BaseType):

  """
  .. class:: ComponentsActivityMonitoring
  """
  ########################################################################

  def __init__(self):
    super(ComponentsActivityMonitoring, self).__init__()

    """ c'tor

    :param self: self reference
    """

    self.keyFields = ["site", "componentType", "componentName"]

    self.monitoringFields = ["Connections", "Queries", "CPU",
                             "MEM", "PendingQueries", "ActiveQueries",
                             "RunningThreads", "MaxFD"]

    self.doc_type = "ComponentsActivityMonitoring"

    self.addMapping({"site": {"type": "keyword"}, "componentType": {"type": "keyword"},
                     "componentName": {"type": "keyword"}})

    self.dataToKeep = 86400 * 30

    self.period = "month"

    self.checkType()
