##
# File:  WorkManagerWebApp.py
# Date:  23-Apr-2015
#
# Updates:
#  10-Dec-2024 zf  added refreshing "latency of servers" report
#  28-Oct-2026     annotator batch console (/service/workmanager/console_*)
##
"""
Chemeditor web request and response processing modules.

This software was developed as part of the World Wide Protein Data Bank
Common Deposition and Annotation System Project

Copyright (c) 2015 wwPDB

This software is provided under a Creative Commons Attribution 3.0 Unported
License described at http://creativecommons.org/licenses/by/3.0/.

"""
__docformat__ = "restructuredtext en"
__author__ = "Zukang Feng"
__email__ = "zfeng@rcsb.rutgers.edu"
__license__ = "Creative Commons Attribution 3.0 Unported"
__version__ = "V0.07"


import pickle as pickle

import datetime
import os
import sys
import traceback

from wwpdb.utils.config.ConfigInfo import ConfigInfo
from wwpdb.apps.wf_engine.engine.WFEapplications import getPicklePath
from wwpdb.utils.session.WebRequest import InputRequest, ResponseContent
from wwpdb.apps.console.console.ops import ConsoleOps
#


class ConsoleWebApp(object):
    """Handle request and response object processing for release module web application.

    """
    def __init__(self, parameterDict=None, verbose=False, log=sys.stderr, siteId="WWPDB_DEV"):
        """
        Create an instance of `WorkManagerWebApp` to manage a release module web request.

         :param `parameterDict`: dictionary storing parameter information from the web request.
             Storage model for GET and POST parameter data is a dictionary of lists.
         :param `verbose`:  boolean flag to activate verbose logging.
         :param `log`:      stream for logging.

        """
        if parameterDict is None:
            parameterDict = {}
        self.__verbose = verbose
        self.__lfh = log
        self.__debug = False
        self.__siteId = siteId
        self.__cI = ConfigInfo(self.__siteId)
        self.__topPath = self.__cI.get('SITE_WEB_APPS_TOP_PATH')
        #

        if type(parameterDict) == dict:  # noqa: E721
            self.__myParameterDict = parameterDict
        else:
            self.__myParameterDict = {}

        if (self.__verbose):
            self.__lfh.write("+WorkManagerWebApp.__init() - REQUEST STARTING ------------------------------------\n")
            self.__lfh.write("+WorkManagerWebApp.__init() - dumping input parameter dictionary \n")
            self.__lfh.write("%s" % (''.join(self.__dumpRequest())))

        self.__reqObj = InputRequest(self.__myParameterDict, verbose=self.__verbose, log=self.__lfh)

        self.__topSessionPath = self.__cI.get('SITE_WEB_APPS_TOP_SESSIONS_PATH')
        self.__templatePath = os.path.join(self.__topPath, "htdocs", "wfm", "templates")
        #
        self.__reqObj.setValue("TopSessionPath", self.__topSessionPath)
        self.__reqObj.setValue("TemplatePath", self.__templatePath)
        self.__reqObj.setValue("TopPath", self.__topPath)
        self.__reqObj.setValue("WWPDB_SITE_ID", self.__siteId)
        self.__reqObj.setValue("current_dep_url", self.__cI.get('SITE_CURRENT_DEP_URL'))
        os.environ["WWPDB_SITE_ID"] = self.__siteId  # EP: Why is this being set?
        #
        # project_version = ProjectVersionInfo(self.__siteId).getVersion()
        # if project_version:
        #     self.__reqObj.setValue("DAVersion", project_version)
        #
        self.__reqObj.setReturnFormat(return_format="html")
        #
        if (self.__verbose):
            self.__lfh.write("-----------------------------------------------------\n")
            self.__lfh.write("+WorkManagerWebApp.__init() Leaving _init with request contents\n")
            self.__reqObj.printIt(ofh=self.__lfh)
            self.__lfh.write("---------------WorkManagerWebApp - done -------------------------------\n")
            self.__lfh.flush()

    def doOp(self):
        """ Execute request and package results in response dictionary.

        :Returns:
             A dictionary containing response data for the input request.
             Minimally, the content of this dictionary will include the
             keys: CONTENT_TYPE and REQUEST_STRING.
        """
        stw = ConsoleWebAppWorker(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        rC = stw.doOp()
        if (self.__debug):
            rqp = self.__reqObj.getRequestPath()
            self.__lfh.write("+WorkManagerWebApp.doOp() operation %s\n" % rqp)
            self.__lfh.write("+WorkManagerWebApp.doOp() return format %s\n" % self.__reqObj.getReturnFormat())
            if rC is not None:
                self.__lfh.write("%s" % (''.join(rC.dump())))
            else:
                self.__lfh.write("+WorkManagerWebApp.doOp() return object is empty\n")

        #
        # Package return according to the request return_format -
        #
        return rC.get()

    def __dumpRequest(self):
        """Utility method to format the contents of the internal parameter dictionary
           containing data from the input web request.

           :Returns:
               ``list`` of formatted text lines
        """
        retL = []
        retL.append("\n-----------------WorkManagerWebApp().__dumpRequest()-----------------------------\n")
        retL.append("Parameter dictionary length = %d\n" % len(self.__myParameterDict))
        for k, vL in self.__myParameterDict.items():
            retL.append("Parameter %30s :" % k)
            for v in vL:
                retL.append(" ->  %s\n" % v)
        retL.append("-------------------------------------------------------------\n")
        return retL


class ConsoleWebAppWorker(object):
    def __init__(self, reqObj=None, verbose=False, log=sys.stderr):
        """
         Worker methods for the chemical component editor application

         Performs URL - application mapping and application launching
         for chemical component editor tool.

         All operations can be driven from this interface which can
         supplied with control information from web application request
         or from a testing application.
        """
        self.__verbose = verbose
        self.__lfh = log
        self.__reqObj = reqObj
        self.__siteId = str(self.__reqObj.getValue("WWPDB_SITE_ID"))
        self.__cI = ConfigInfo(self.__siteId)
        #
        self.__appPathD = {'/service/environment/dump': '_dumpOp',
                           '/service/console/console_login': '_ConsoleLoginOp',
                           '/service/console/console_logout': '_ConsoleLogoutOp',
                           '/service/console/console_whoami': '_ConsoleWhoamiOp',
                           '/service/console/console_start': '_ConsoleStartOp',
                           '/service/console/console_status': '_ConsoleStatusOp',
                           '/service/console/console_cancel': '_ConsoleCancelOp',
                           }

    def doOp(self):
        """Map operation to path and invoke operation.

            :Returns:

            Operation output is packaged in a ResponseContent() object.
        """
        return self.__doOpException()

    def __doOpException(self):
        """Map operation to path and invoke operation.  Exceptions are caught within this method.

            :Returns:

            Operation output is packaged in a ResponseContent() object.
        """
        #
        try:
            reqPath = self.__reqObj.getRequestPath()
            if reqPath not in self.__appPathD:
                # bail out if operation is unknown -
                rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
                rC.setError(errMsg='Unknown operation')
            else:
                mth = getattr(self, self.__appPathD[reqPath], None)
                rC = mth()
            return rC
        except:  # noqa: E722 pylint: disable=bare-except
            traceback.print_exc(file=self.__lfh)
            rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
            rC.setError(errMsg='Operation failure')
            return rC

    ################################################################################################################
    # ------------------------------------------------------------------------------------------------------------
    #      Top-level REST methods
    # ------------------------------------------------------------------------------------------------------------
    #
    def _dumpOp(self):
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        rC.setHtmlList(self.__reqObj.dump(format='html'))
        return rC

    def _consoleOps(self):
        self.__getSession()
        return ConsoleOps(
            reqObj=self.__reqObj,
            session_id=self.__sessionId,
            session_path=self.__sessionPath,
            site_id=self.__siteId,
            verbose=self.__verbose,
            log=self.__lfh,
        )

    def _ConsoleLoginOp(self):
        return self._consoleOps().login()

    def _ConsoleLogoutOp(self):
        return self._consoleOps().logout()

    def _ConsoleWhoamiOp(self):
        return self._consoleOps().whoami()

    def _ConsoleStartOp(self):
        return self._consoleOps().start()

    def _ConsoleStatusOp(self):
        return self._consoleOps().status()

    def _ConsoleCancelOp(self):
        return self._consoleOps().cancel()

    def __returnJsonObject(self, successful_msg, failed_msg):
        """ return json object
        """
        self.__reqObj.setReturnFormat(return_format="json")
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        if failed_msg:
            rC.setError(errMsg=failed_msg)
        else:
            rC.setText(text=successful_msg)
        #
        return rC

    def __returnJsonDict(self, rtrnDict):
        self.__reqObj.setReturnFormat(return_format="json")
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        rC.addDictionaryItems(rtrnDict)
        return rC

    def __allow_or_prevent_op(self, op, function, pickle_file, successful_msg, failed_msg):
        if (self.__verbose):
            self.__lfh.write("+WorkManagerWebAppWorker.%s Starting now\n" % function)
        #
        storage_pickle_path = self.__get_deposit_storage_pickle_path(pickle_file)
        text = ''
        error = ''
        try:
            if op == 'allow':
                self.__dump_deposit_storage_pickle(storage_pickle_path, 'Unlocked by Annotator from WFM')
            elif op == 'prevent':
                if os.path.exists(storage_pickle_path):
                    os.remove(storage_pickle_path)
                #
            #
            text = successful_msg
        except:  # noqa: E722 pylint: disable=bare-except
            error = failed_msg
        #
        return self.__returnJsonObject(text, error)

    def __get_deposit_storage_pickle_path(self, pickle_file):
        """
        """
        spath = getPicklePath(str(self.__reqObj.getValue("identifier")))
        if spath:
            return os.path.join(spath, pickle_file)
        else:
            return None

    def __dump_deposit_storage_pickle(self, storage_pickle_path, reason):
        """
        """
        data = {}
        data['annotator_initials'] = str(self.__reqObj.getValue("annotator"))
        data['reason'] = reason
        data['date'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f = open(storage_pickle_path, 'wb')
        pickle.dump(data, f)
        f.close()

    def __getSession(self):
        """ Join existing session or create new session as required.
        """
        #
        # pylint: disable=attribute-defined-outside-init
        self.__sObj = self.__reqObj.newSessionObj()
        self.__sessionId = self.__sObj.getId()
        self.__sessionPath = self.__sObj.getPath()
        # self.__rltvSessionPath = self.__sObj.getRelativePath()
        # pylint: enable=attribute-defined-outside-init
        if (self.__verbose):
            self.__lfh.write("------------------------------------------------------\n")
            self.__lfh.write("+WorkManagerWebAppWorker.__getSession() - creating/joining session %s\n" % self.__sessionId)
            self.__lfh.write("+WorkManagerWebAppWorker.__getSession() - session path %s\n" % self.__sessionPath)

    def __processTemplate(self, fn, parameterDict=None):
        """ Read the input HTML template data file and perform the key/value substitutions in the
            input parameter dictionary.

            :Params:
                ``parameterDict``: dictionary where
                key = name of subsitution placeholder in the template and
                value = data to be used to substitute information for the placeholder

            :Returns:
                string representing entirety of content with subsitution placeholders now replaced with data
        """
        if parameterDict is None:
            parameterDict = {}
        tPath = self.__reqObj.getValue("TemplatePath")
        fPath = os.path.join(tPath, fn)
        ifh = open(fPath, 'r')
        sIn = ifh.read()
        ifh.close()
        return (sIn % parameterDict)
