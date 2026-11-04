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

try:
    import cPickle as pickle
except ImportError:
    import pickle as pickle

import datetime
import os
import subprocess
import sys
import time
import traceback

from wwpdb.utils.config.ConfigInfo import ConfigInfo
from wwpdb.apps.wf_engine.engine.WFEapplications import reRunWorkflow, getPicklePath
#from wwpdb.utils.detach.DetachUtils import DetachUtils
#from wwpdb.io.locator.PathInfo import PathInfo
from wwpdb.utils.session.WebRequest import InputRequest, ResponseContent
from wwpdb.utils.session.WebUploadUtils import WebUploadUtils
#from wwpdb.utils.config.ProjectVersionInfo import ProjectVersionInfo
#from wwpdb.apps.msgmodule.util.AutoMessage import AutoMessage
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
#                           '/service/workmanager/login': '_LoginOp',
#                           '/service/workmanager/logout': '_LogoutOp',
#                           '/service/workmanager/summary': '_SummaryOp',
#                           '/service/workmanager/replacementhist': '_ReplacementHistOp',
#                           '/service/workmanager/snapshotdiff': '_SnapshotDiffOp',
#                           '/service/workmanager/getpassword': '_PasswordOp',
#                           '/service/workmanager/milestonearchive': '_MilestoneOp',
#                           '/service/workmanager/milestonereset': '_MilestoneResetOp',
#                           '/service/workmanager/allowupload': '_AllowUploadOp',
#                           '/service/workmanager/preventupload': '_PreventUploadOp',
#                           '/service/workmanager/enableftpupload': '_EnableFtpUploadOp',
#                           '/service/workmanager/allowsubmit': '_AllowSubmitOp',
#                           '/service/workmanager/preventsubmit': '_PreventSubmitOp',
#                           '/service/workmanager/rerunworkflow': '_RerunWorkFlowOp',
                           # '/service/workmanager/killworkflow': '_KillWorkFlowOp',
                           # '/service/workmanager/ciffile': '_DownloadCifFileOp',
                           # '/service/workmanager/logfile': '_DownloadLogFileOp',
                           # '/service/workmanager/filereports': '_ViewAllFileOp',
                           # '/service/workmanager/gettabledata': '_GetTableDataOp',
                           # '/service/workmanager/search': '_SearchPageOp',
                           # '/service/workmanager/edit_my_list': '_EditMyListOp',
                           # '/service/workmanager/refresh': '_RefreshOp',
                           # '/service/workmanager/runengine': '_RunEngineOp',
                           # '/service/workmanager/assign': '_AssignOp',
                           # '/service/workmanager/level2': '_Level2PageOp',
                           # '/service/workmanager/edituserdata': '_EditUserOp',
                           # '/service/workmanager/saveuserdata': '_SaveUserOp',
                           # '/service/workmanager/changeprivilege': '_ChangePrivilege',
                           # '/service/workmanager/changeactiveuser': '_ChangeActiveUser',
                           # '/service/workmanager/start_group_workflow': '_GroupEngineDepictOp',
                           # '/service/workmanager/start_group_worktask': '_GroupTaskDepictOp',
                           # '/service/workmanager/get_task_message': '_GetGroupTaskMessageOp',
                           # '/service/workmanager/remove_task_message': '_RemoveGroupTaskMessageOp',
                           # '/service/workmanager/get_ligand_list': '_GetLigandListOp',
                           # '/service/workmanager/run_group_engine': '_RunGroupEngineOp',
                           # '/service/workmanager/run_group_tasks': '_RunGroupTasksOp',
                           # '/service/workmanager/open_editing_page': '_LaunchEditingPageOp',
                           # '/service/workmanager/submit_editing_form': '_ProcessEditingFormOp',
                           # '/service/workmanager/check_editing_form_status': '_CheckEditingFormStatusOp',
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

    # def __doOpNoException(self):
    #     """Map operation to path and invoke operation.  No exception handling is performed.

    #         :Returns:

    #         Operation output is packaged in a ResponseContent() object.
    #     """
    #     #
    #     reqPath = self.__reqObj.getRequestPath()
    #     if reqPath not in self.__appPathD:
    #         # bail out if operation is unknown -
    #         rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #         rC.setError(errMsg='Unknown operation')
    #         return rC
    #     else:
    #         mth = getattr(self, self.__appPathD[reqPath], None)
    #         rC = mth()
    #     return rC

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

    # def _LoginOp(self):
    #     """ Launch first-level interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._LoginOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     username = str(self.__reqObj.getValue('username'))
    #     password = str(self.__reqObj.getValue('password'))
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     userInfo = db.Autenticate(username, password)
    #     if userInfo:
    #         readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='level1_config.cif', verbose=self.__verbose, log=self.__lfh)
    #         configDict = readUtil.read()
    #         depictUtil = DepictLevel1(reqObj=self.__reqObj, statusDB=db, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
    #         rC.setHtmlText(depictUtil.getPageText(page_id='level1_tmplt'))
    #     else:
    #         myD = {}
    #         myD['sessionid'] = self.__sessionId
    #         myD['message'] = 'Invalid Login'
    #         rC.setHtmlText(self.__processTemplate('login_tmplt.html', myD))
    #     #
    #     return rC

    # def _LogoutOp(self):
    #     """ Logout first-level interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._LogoutOp() logout\n")
    #     #
    #     self.__getSession()
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     myD = {}
    #     myD['sessionid'] = ''
    #     myD['message'] = ''
    #     rC.setHtmlText(self.__processTemplate('login_tmplt.html', myD))
    #     #
    #     return rC

    # def _SummaryOp(self):
    #     """ Summary page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._SummaryOp() Starting now\n")
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='summary_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictOther(reqObj=self.__reqObj, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
    #     depictUtil.SummaryPage()
    #     rC.setHtmlText(depictUtil.getPageText(page_id='summary_tmplt'))
    #     #
    #     return rC

    # def _ReplacementHistOp(self):
    #     """ Author initiated replacement history page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._ReplacementHistOp() Starting now\n")
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='replacement_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictOther(reqObj=self.__reqObj, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
    #     depictUtil.ReplacementPage()
    #     rC.setHtmlText(depictUtil.getPageText(page_id='replacement_tmplt'))
    #     #
    #     return rC

    # def _SnapshotDiffOp(self):
    #     """ Summary page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._SnapshotDiffOp() Starting now\n")
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     snapshot = DepictSnapShot(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     rC.setHtmlText(snapshot.getPageText())
    #     #
    #     return rC

    # def _PasswordOp(self):
    #     """ Get Entry password
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._PasswordOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     deppw, error = self.__getPassword(depositionid)
    #     return self.__returnJsonObject(deppw, error)

    # def __getPassword(self, depositionid):
    #     """ Get password for entry depositionid
    #     """
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     depInfo = db.getDepInfo(depositionid=depositionid)
    #     #
    #     deppw = ''
    #     if depInfo and ('deppw' in depInfo) and depInfo['deppw']:
    #         deppw = str(depInfo['deppw'])
    #     #
    #     error = ''
    #     if not deppw:
    #         error = "Can't find password for entry " + depositionid
    #     #
    #     return deppw, error

    # def _MilestoneOp(self):
    #     """ Copy model milestone file
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._MilestoneOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     msf = MileStoneFile(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     error = ''
    #     if not msf.getInputFile(depositionid, 'archive', 'model', 'pdbx', 'latest'):
    #         error = "Can't find model file for entry " + depositionid + ' in archive directory.'
    #     elif not msf.getOutputFile(depositionid, 'archive', 'model-annotate', 'pdbx', 'next'):
    #         error = 'Copy model-annotate file failed for entry ' + depositionid + '.'
    #     #
    #     return self.__returnJsonObject('Successfully wrote milestone file', error)

    # def _MilestoneResetOp(self):
    #     """ Reset model milestone file
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._MilestoneResetOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     msf = MileStoneFile(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     lastInst = db.getLastInstance(depositionid=depositionid)
    #     if lastInst and ('dep_exp_method' in lastInst) and str(lastInst['dep_exp_method']).upper() in \
    #        ('ELECTRON CRYSTALLOGRAPHY', 'CRYO-ELECTRON MICROSCOPY', 'ELECTRON TOMOGRAPHY', 'ELECTRON MICROSCOPY'):
    #         msf.setEmEntry()
    #     #
    #     error = ''
    #     if not msf.getInputFile(depositionid, 'archive', 'model', 'pdbx', 'latest'):
    #         error = "Can't find model file for entry " + depositionid + ' in archive directory.'
    #     elif not msf.getOutputFile(depositionid, 'deposit', 'model', 'pdbx', 'next'):
    #         error = 'Copy model file to deposit failed for entry ' + depositionid + '.'
    #     #
    #     return self.__returnJsonObject('OK', error)

    # def _AllowUploadOp(self):
    #     """ Allow file to be uploaded in DepUI
    #     """
    #     return self.__allow_or_prevent_op('allow', '_AllowUploadOp()', 'uploadOK.pkl',
    #                                       'You have set this deposition to allow bad uploads !',
    #                                       'Failed to allow incomplete upload !')

    # def _PreventUploadOp(self):
    #     """ Prevent file to be uploaded in DepUI
    #     """
    #     return self.__allow_or_prevent_op('prevent', '_PreventUploadOp()', 'uploadOK.pkl',
    #                                       'You have prevented bad uploads !', 'Failed to block incomplete upload !')

    # def _AllowSubmitOp(self):
    #     """ Allow entry to be submit in DepUI
    #     """
    #     return self.__allow_or_prevent_op('allow', '_AllowSubmitOp()', 'submitOK.pkl',
    #                                       'You have set this deposition to allow incomplete Deposition !',
    #                                       'Failed to allow incomplete submission !')

    # def _PreventSubmitOp(self):
    #     """ Prevent entry to be submit in DepUI
    #     """
    #     return self.__allow_or_prevent_op('prevent', '_PreventSubmitOp()', 'submitOK.pkl',
    #                                       'You have prevented incomplete Deposition !', 'Failed to block incomplete submission !')

    # def _EnableFtpUploadOp(self):
    #     """ Allow ftp upload file
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._EnableFtpUploadOp() Starting now\n")
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     userFile = self.__cI.get('FTP_USER_FILE')
    #     userDbFile = self.__cI.get('FTP_DB_FILE')
    #     ftpPath = self.__cI.get('FTP_STORAGE_PATH')
    #     error = ''
    #     try:
    #         ftpDir = os.path.join(ftpPath, depositionid)
    #         if not os.path.exists(ftpDir):
    #             cmd = ['mkdir', '-p', ftpDir]
    #             subprocess.check_call(cmd)
    #         #
    #     except Exception as e:
    #         self.__lfh.write("+WorkManagerWebAppWorker._EnableFtpUploadOp() Failed to create FTP user folder %s\n" % str(e))
    #         error = 'Failed to create FTP user folder'
    #     #
    #     try:
    #         with open(userFile, 'r') as infile:
    #             data = infile.read()
    #             if depositionid not in data:
    #                 depPW, _err = self.__getPassword(depositionid)
    #                 if depPW:
    #                     outfile = open(userFile, 'a')
    #                     outfile.write(depositionid + '\n' + depPW + '\n')
    #                     outfile.close()
    #                     cmd = ['db_load', '-T', '-t', 'hash', '-f', userFile, userDbFile]
    #                     subprocess.check_call(cmd)
    #                 else:
    #                     if error:
    #                         error += '; '
    #                     #
    #                     error += "Can't find password for entry " + depositionid
    #                 #
    #             #
    #         #
    #     except Exception as e:
    #         self.__lfh.write("+WorkManagerWebAppWorker._EnableFtpUploadOp() Failed to add FTP user %s : %s\n" % (depositionid, str(e)))
    #         if error:
    #             error += '; '
    #         #
    #         error += 'Failed to add FTP user'
    #     #
    #     if error:
    #         return self.__returnJsonObject('', error)
    #     #
    #     text = ''
    #     try:
    #         # create a pickle file, which is used to check if FTP upload was allowed
    #         storage_pickle_path = self.__get_deposit_storage_pickle_path('externalUpload.pkl')
    #         self.__dump_deposit_storage_pickle(storage_pickle_path, 'File upload in depUI failed; FTP upload enabled by Annotator from WFM')
    #         # send instructions email to depositor
    #         subject = 'Instructions for wwPDB FTP upload for deposition ' + depositionid
    #         myD = {}
    #         myD['depositionid'] = depositionid
    #         myD['ftp_host_name'] = self.__cI.get('FTP_HOST_NAME')
    #         myD['ftp_port_number'] = self.__cI.get('FTP_PORT_NUMBER')
    #         myD['ftp_connect_details_0'] = self.__cI.get('FTP_CONNECT_DETAILS')[0]
    #         myD['ftp_connect_details_1'] = self.__cI.get('FTP_CONNECT_DETAILS')[1]
    #         myD['site_dep_email_url'] = self.__cI.get('SITE_DEP_EMAIL_URL')
    #         message = self.__processTemplate('ftp_message.txt', myD)
    #         am = AutoMessage(siteId=self.__siteId)
    #         ret = am.sendSingleMessage(depositionid, subject, message, p_tmpltType="instruction-ftp")  # CS 2024-04-04 add template type
    #         text = 'FTP upload enabled; email sent to the user'
    #         self.__lfh.write("+WorkManagerWebAppWorker._EnableFtpUploadOp() sent message status=%s\n" % ret)
    #     except Exception as e:
    #         self.__lfh.write("+WorkManagerWebAppWorker._EnableFtpUploadOp() Failed to enable file import and/or send instructions to the depositor %s\n" % str(e))
    #         error = 'Failed in enable file import to depUI; instructions not sent'
    #     #
    #     return self.__returnJsonObject(text, error)

    # def _RerunWorkFlowOp(self):
    #     """ Re-run work flow
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RerunWorkFlowOp() Starting now\n")
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     status = reRunWorkflow(depositionid)
    #     text = ''
    #     error = ''
    #     if status == 'OK':
    #         text = 'You have restart the Workflow !'
    #     else:
    #         error = 'Rerun was not set ' + status
    #     #
    #     return self.__returnJsonObject(text, error)

    # def _KillWorkFlowOp(self):
    #     """ Kill work flow
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._KillWorkFlowOp() Starting now\n")
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     status = db.killWorkFlow(depositionid=depositionid)
    #     error = ''
    #     if not status == 'OK':
    #         error = status
    #     #
    #     return self.__returnJsonObject(status, error)

    # def _DownloadCifFileOp(self):
    #     """ Download model cif file
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._DownloadCifFileOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     filesource = str(self.__reqObj.getValue("filesource"))
    #     version = str(self.__reqObj.getValue("version"))
    #     instance = str(self.__reqObj.getValue("instance"))
    #     #
    #     pI = PathInfo(siteId=self.__siteId, sessionPath=self.__sessionPath, verbose=self.__verbose, log=self.__lfh)
    #     filePath = pI.getFilePath(dataSetId=depositionid, wfInstanceId=instance, contentType='model', formatType='pdbx',
    #                               fileSource=filesource, versionId=version, partNumber='1')
    #     #
    #     self.__reqObj.setReturnFormat(return_format="binary")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     rC.setBinaryFile(filePath, attachmentFlag=True, serveCompressed=False)
    #     return rC

    # def _DownloadLogFileOp(self):
    #     """ Download latest version model cif file
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._DownloadLogFileOp() Starting now\n")
    #     #
    #     logUtil = LogFileUtil(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     filePath = logUtil.getLogFile()
    #     #
    #     self.__reqObj.setReturnFormat(return_format="binary")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     rC.setBinaryFile(filePath, attachmentFlag=True, serveCompressed=False)
    #     return rC

    # def _ViewAllFileOp(self):
    #     """ View all files page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._ViewAllFileOp() Starting now\n")
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='allfile_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictOther(reqObj=self.__reqObj, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
    #     depictUtil.AllFilePage()
    #     rC.setHtmlText(depictUtil.getPageText(page_id='allfile_tmplt'))
    #     #
    #     return rC

    # def _GetTableDataOp(self):
    #     """ return table data content
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._GetTableDataOp() Starting now\n")
    #     #
    #     self.__getSession()
    #     #
    #     data = loadPickleFile(self.__sessionPath, self.__reqObj.getValue("picklefile"))
    #     if not data:
    #         data = []
    #     #
    #     rtrnDict = {}
    #     rtrnDict['table_rows'] = data
    #     return self.__returnJsonDict(rtrnDict)

    # def _SearchPageOp(self):
    #     """ Search Page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._SearchPageOp() Starting now\n")
    #     #
    #     sUtil = SearchUtil(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     sUtil.updateSql()
    #     return self.__refreshTableContent(None, self.__reqObj.getValue('index'), False)

    # def _EditMyListOp(self):
    #     """ Add to/Remove from my list interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._EditMyListOp() Starting now\n")
    #     #
    #     depositionid = self.__reqObj.getValue("identifier")
    #     annotator = self.__reqObj.getValue("annotator")
    #     type = self.__reqObj.getValue("type")  # pylint: disable=redefined-builtin
    #     sdb = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     if type == 'add':
    #         sdb.addToMyList(depositionid, annotator)
    #     else:
    #         sdb.removeFromMyList(depositionid)
    #     #
    #     return self.__refreshTableContent(sdb, 'all', False)

    # def _RefreshOp(self):
    #     """ Refresh list interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RefreshOp() Starting now\n")
    #     #
    #     return self.__refreshTableContent(None, self.__reqObj.getValue('index'), True)

    # def _RunEngineOp(self):
    #     """ Run work flow engine interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RunEngineOp() Starting now\n")
    #     #
    #     type = str(self.__reqObj.getValue("type"))  # pylint: disable=redefined-builtin
    #     depositionid = str(self.__reqObj.getValue("identifier"))
    #     instanceid = str(self.__reqObj.getValue("instance"))
    #     classid = str(self.__reqObj.getValue("classID"))
    #     command = str(self.__reqObj.getValue("command"))
    #     version = str(self.__reqObj.getValue("version"))
    #     # method = str(self.__reqObj.getValue("method"))
    #     #
    #     sdb = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     if type == 'kill':
    #         classInfo = sdb.getWfClassByID(classID='Annotate')
    #     else:
    #         classInfo = sdb.getWfClassByID(classID=classid)
    #     if not classInfo:
    #         return self.__returnJsonObject('', "Start '" + classid + "' workflow failed.")
    #     #
    #     classFileName = classInfo['class_file']
    #     if type != 'rerun_single_module':
    #         if classFileName.find(".bf.xml") < 0:
    #             classFileName = 'Annotation.bf.xml:' + str(classid)
    #         #
    #     #
    #     dep_status = sdb.getDepositionStatus(depositionid=depositionid, instid=instanceid, classid=classid)
    #     com_status = sdb.getCommandStatus(depositionid=depositionid)
    #     startWF = False
    #     if type == 'init':
    #         if dep_status == 'INIT' and com_status == 'INIT':
    #             startWF = True
    #         #
    #     elif type == 'open':
    #         if dep_status == 'OPEN' and com_status == 'WORKING':
    #             startWF = True
    #         #
    #     elif type == 'restart':
    #         if com_status != 'INIT':
    #             msf = MileStoneFile(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #             msf.getInputFile(depositionid, 'archive', 'model', 'pdbx', 'original')
    #             msf.getOutputFile(depositionid, 'archive', 'model', 'pdbx', 'next')
    #             startWF = True
    #         #
    #     else:
    #         startWF = True
    #     #
    #     if not startWF:
    #         return self.__returnJsonObject('OK', '')
    #     #
    #     time.sleep(0.5)
    #     msg = sdb.insertCommunicationCommand(depositionid=depositionid, instid=instanceid, classid=classid, command=command,
    #                                          classname=classFileName, dataversion=version)
    #     if msg != 'OK':
    #         return self.__returnJsonObject('', msg)
    #     else:
    #         return self.__returnJsonObject(msg, '')
    #     #

    # def _AssignOp(self):
    #     """ Assign interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._AssignOp() Starting now\n")
    #     #
    #     assign_pair_list = []
    #     assigned_data = str(self.__reqObj.getValue("assigned_data")).replace(' ', '').strip()
    #     slist = assigned_data.split(',')
    #     for pair in slist:
    #         list1 = pair.split(':')
    #         assign_pair_list.append(list1)
    #     #
    #     assignUtil = AnnotAssignUtil(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     assignUtil.updateAnnotatorAssignment(assignList=assign_pair_list)
    #     #
    #     sdb = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     sdb.updateAnnotatorAssignment(assignList=assign_pair_list)
    #     #
    #     return self.__refreshTableContent(sdb, str(self.__reqObj.getValue("tab_id")) + "_table_1", False)

    # def _Level2PageOp(self):
    #     """ Level2 page interface
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._Level2PageOp() Starting now\n")
    #     #
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='level_2_3_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictOther(reqObj=self.__reqObj, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     level = str(self.__reqObj.getValue("level"))
    #     if level == 'level3':
    #         depictUtil.getLevelPageSetting('level3_tmplt')
    #         rC.setHtmlText(depictUtil.getPageText(page_id='level3_tmplt'))
    #     else:
    #         depictUtil.getLevelPageSetting('level2_tmplt')
    #         rC.setHtmlText(depictUtil.getPageText(page_id='level2_tmplt'))
    #     #
    #     return rC

    # def _EditUserOp(self):
    #     """ Edit User Information
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._EditUserOp() Starting now\n")
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     user = str(self.__reqObj.getValue('user'))
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     userInfo = db.getUserByName(username=user)
    #     if userInfo:
    #         userInfo['sessionid'] = str(self.__reqObj.getValue('sessionid'))
    #         rC.setHtmlText(self.__processTemplate('edit_user_tmplt.html', userInfo))
    #     else:
    #         myD = {}
    #         myD['message'] = 'Invalid user name: ' + user
    #         rC.setHtmlText(self.__processTemplate('exit_user_tmplt.html', myD))
    #     #
    #     return rC

    # def _SaveUserOp(self):
    #     """ Save User Information
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._SaveUserOp() Starting now\n")
    #     #
    #     successful_msg = ''
    #     failed_msg = ''
    #     user_name = self.__reqObj.getValue('user_name')
    #     data = {}
    #     for item in ('password', 'email', 'initials', 'first_name', 'last_name', 'da_group_id'):
    #         val = self.__reqObj.getValue(item)
    #         if val:
    #             data[item] = val
    #         #
    #     #
    #     if user_name and data:
    #         db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #         ret = db.runUpdate(table='da_users', where={'user_name': user_name}, data=data)
    #         if not ret or ret != 'OK':
    #             failed_msg = 'Update user information failed.'
    #         else:
    #             successful_msg = 'User Information Updated.'
    #         #
    #     else:
    #         failed_msg = 'Update user information failed.'
    #     #
    #     tab_id = self.__reqObj.getValue('tab_id')
    #     if tab_id:
    #         return self.__returnJsonObject(successful_msg, failed_msg)
    #     else:
    #         self.__reqObj.setReturnFormat(return_format="html")
    #         rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #         myD = {}
    #         if failed_msg:
    #             myD['message'] = failed_msg
    #         else:
    #             myD['message'] = successful_msg
    #         #
    #         rC.setHtmlText(self.__processTemplate('exit_user_tmplt.html', myD))
    #         return rC
    #     #

    # def _ChangePrivilege(self):
    #     """ Change da_users.da_group_id
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._ChangePrivilege() Starting now\n")
    #     #
    #     user_name_list = self.__reqObj.getValue('user_names').split(',')
    #     if not user_name_list:
    #         return self.__returnJsonObject('', 'No user information provided.')
    #     #
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     if db:
    #         UserInfo = db.getUserByInitial(initial=self.__reqObj.getValue('annotator'))
    #         if UserInfo and ('site' in UserInfo):
    #             GroupInfo = db.getSiteGroupWithCode(site=UserInfo['site'], code=self.__reqObj.getValue('code'))
    #             if GroupInfo and ('group_id' in GroupInfo):
    #                 for user_name in user_name_list:
    #                     _ret = db.runUpdate(table='da_users', where={'user_name': user_name}, data={'da_group_id': str(GroupInfo['group_id'])})  # noqa: F841
    #                 #
    #             else:
    #                 return self.__returnJsonObject('', 'Change privilege failed.')
    #             #
    #         else:
    #             return self.__returnJsonObject('', 'Change privilege failed.')
    #         #
    #     else:
    #         return self.__returnJsonObject('', 'Change privilege failed.')
    #     #
    #     return self.__returnUpdatePage(db)

    # def _ChangeActiveUser(self):
    #     """ Change da_users.active
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._ChangeActiveUser() Starting now\n")
    #     #
    #     user_name_list = self.__reqObj.getValue('user_names').split(',')
    #     if not user_name_list:
    #         return self.__returnJsonObject('', 'No user information provided.')
    #     #
    #     db = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     for user_name in user_name_list:
    #         active = self.__reqObj.getValue(user_name)
    #         if not active:
    #             continue
    #         #
    #         _ret = db.runUpdate(table='da_users', where={'user_name': user_name}, data={'active': active})  # noqa: F841
    #     #
    #     return self.__returnUpdatePage(db)

    # def _GroupEngineDepictOp(self):
    #     """ Depict Start Workflow Engine Page for entries under group deposition
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._GroupEngineDepictOp() Starting now\n")
    #     #
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='group_level_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictGroup(reqObj=self.__reqObj, conFigObj=configDict, workFlow=True, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     rC.setHtmlText(depictUtil.getPageText(page_id='group_workflow_tmplt'))
    #     return rC

    # def _GroupTaskDepictOp(self):
    #     """ Depict Start Workflow Engine Page for entries under group deposition
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._GroupTaskDepictOp() Starting now\n")
    #     #
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='group_level_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictGroup(reqObj=self.__reqObj, conFigObj=configDict, workFlow=False, verbose=self.__verbose, log=self.__lfh)
    #     #
    #     self.__reqObj.setReturnFormat(return_format="html")
    #     rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     rC.setHtmlText(depictUtil.getPageText(page_id='group_worktask_tmplt'))
    #     return rC

    # def _GetGroupTaskMessageOp(self):
    #     """ Get group task log message based on task key
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._GetGroupTaskMessageOp() Starting now\n")
    #     #
    #     taskUtil = BaseClass(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     return self.__returnJsonObject(taskUtil.getMessage(), "")

    # def _RemoveGroupTaskMessageOp(self):
    #     """ Remove group task log message based on task key
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RemoveGroupTaskMessageOp() Starting now\n")
    #     #
    #     taskUtil = BaseClass(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     message = taskUtil.removeMessage()
    #     if message != "OK":
    #         return self.__returnJsonObject("", message)
    #     #
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='group_level_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictGroup(reqObj=self.__reqObj, conFigObj=configDict, workFlow=False, verbose=self.__verbose, log=self.__lfh)
    #     taskInfoTxt = depictUtil.getTaskInfo()
    #     if taskInfoTxt == "":
    #         taskInfoTxt = "empty"
    #     #
    #     return self.__returnJsonObject(taskInfoTxt, "")

    # def _GetLigandListOp(self):
    #     """ Get all ligand IDs associated with the deposited entries in a group
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._GetLigandListOp() Starting now\n")
    #     #
    #     ligFinder = LigandFinder(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
    #     returnMap, errMsg = ligFinder.getLigandInfo()
    #     #
    #     rtrnDict = {}
    #     if returnMap:
    #         rtrnDict['map'] = returnMap
    #     else:
    #         rtrnDict['errorflag'] = True
    #         rtrnDict['errortext'] = errMsg
    #     #
    #     return self.__returnJsonDict(rtrnDict)

    # def _RunGroupEngineOp(self):
    #     """ Run Workflow Engine for selected entries under group deposition
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RunGroupEngineOp() Starting now\n")
    #     #
    #     successful_msg = ''
    #     failed_msg = ''
    #     class_comb = self.__reqObj.getValue('classID')
    #     if not class_comb:
    #         failed_msg = 'No workflow selected'
    #     #
    #     entryList = self.__reqObj.getValueList('entry_id')
    #     if not entryList:
    #         if failed_msg:
    #             failed_msg += '\n'
    #         #
    #         failed_msg += 'No entry selected.'
    #     #
    #     if failed_msg:
    #         return self.__returnJsonObject(successful_msg, failed_msg)
    #     #
    #     c_list = class_comb.split('_')
    #     command = c_list[0]
    #     classid = c_list[1]
    #     if c_list[2] == 'UI':
    #         classid = c_list[1] + c_list[2]
    #     #
    #     version = ''
    #     if command == 'restartGoWF':
    #         version = 'latest'
    #     #
    #     sdb = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
    #     classInfo = sdb.getWfClassByID(classID=classid)
    #     if not classInfo:
    #         return self.__returnJsonObject('', "Start '" + classid + "' workflow failed.")
    #     #
    #     classFileName = classInfo['class_file']
    #     if c_list[2] == 'WF':
    #         if (classFileName != 'Annotation.bf.xml') and (classFileName != 'Annotation.xml') and (classFileName != 'wf_op_annot-main_fs_archive.xml'):
    #             classFileName = 'Annotation.bf.xml:' + str(classid)
    #         #
    #     #
    #     for entry_id in entryList:
    #         if successful_msg:
    #             successful_msg += '\n'
    #         #
    #         instanceid = ''
    #         lastWFInstance = sdb.getLastWFInstance(depositionid=entry_id, classid=classid)
    #         if lastWFInstance and ('wf_inst_id' in lastWFInstance) and lastWFInstance['wf_inst_id']:
    #             instanceid = lastWFInstance['wf_inst_id']
    #         #
    #         msg = sdb.insertCommunicationCommand(depositionid=entry_id, instid=instanceid, classid=classid,
    #                                              command=command, classname=classFileName, dataversion=version)
    #         if msg != 'OK':
    #             successful_msg += msg
    #         else:
    #             successful_msg += "Start '" + classid + "' workflow for '" + entry_id + "'."
    #         #
    #     #
    #     return self.__returnJsonObject(successful_msg, failed_msg)

    # def _RunGroupTasksOp(self):
    #     """ Run tasks for selected entries under group deposition
    #     """
    #     if (self.__verbose):
    #         self.__lfh.write("+WorkManagerWebAppWorker._RunGroupTasksOp() Starting now\n")
    #     #
    #     successful_msg = ''
    #     failed_msg = ''
    #     entryList = self.__reqObj.getValueList('entry_id')
    #     if not entryList:
    #         if failed_msg:
    #             failed_msg += '\n'
    #         #
    #         failed_msg += 'No entry selected.'
    #     #
    #     if failed_msg:
    #         return self.__returnJsonObject(successful_msg, failed_msg)
    #     #
    #     option = self.__reqObj.getValue('option')
    #     if (option == 'cifcheck') or (option == 'mischeck'):
    #         checkUtil = CifChecker(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = checkUtil.run()
    #     elif option == 'copy_to_deposition':
    #         copyUtil = CopyFileToAutoGroup(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = copyUtil.run()
    #     elif option == 'database':
    #         dbLoader = DBLoader(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = dbLoader.run()
    #     elif option == 'annotation':
    #         annTaskUtil = RunAnnotationTask(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = annTaskUtil.run()
    #     elif option == 'ligand':
    #         ligTaskUtil = RunLigandTask(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = ligTaskUtil.run()
    #     elif option == 'pdbfile':
    #         pfGenUtil = PdbFileGenerator(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = pfGenUtil.run()
    #     elif option == 'sequence':
    #         self.__getSession()
    #         #
    #         filePath, errMsg = self.__getTemplateFile()
    #         if errMsg:
    #             return self.__returnJsonObject('', errMsg)
    #         elif not filePath:
    #             return self.__returnJsonObject('', 'No template model file found.')
    #         elif not os.access(filePath, os.F_OK):
    #             return self.__returnJsonObject('', "Template file '" + filePath + "' can not be found.")
    #         #
    #         seqMerger = SequenceMerger(reqObj=self.__reqObj, entryList=entryList, templateFile=filePath, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = seqMerger.run()
    #     elif option == 'validation':
    #         valTaskUtil = RunValidationTask(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = valTaskUtil.run()
    #     elif option == 'status':
    #         stUpdater = StatusUpdater(reqObj=self.__reqObj, entryList=entryList, verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = stUpdater.run()
    #     elif option == 'other':
    #         checkList = self.__reqObj.getValueList('checked_list')
    #         if len(checkList) == 0:
    #             return self.__returnJsonObject('', 'No task selected.')
    #         #
    #         needTemplateFile = False
    #         if (len(checkList) > 1) or (checkList[0] != 'loi'):
    #             needTemplateFile = True
    #         #
    #         self.__getSession()
    #         #
    #         filePath = ''
    #         if needTemplateFile:
    #             filePath, errMsg = self.__getTemplateFile()
    #             if errMsg:
    #                 return self.__returnJsonObject('', errMsg)
    #             elif not filePath:
    #                 return self.__returnJsonObject('', 'No template model file found.')
    #             elif not os.access(filePath, os.F_OK):
    #                 return self.__returnJsonObject('', "Template file '" + filePath + "' can not be found.")
    #             #
    #         #
    #         metaMerger = MetaDataMerger(reqObj=self.__reqObj, entryList=entryList, taskList=checkList, templateFile=filePath,
    #                                     verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = metaMerger.run()
    #     elif option == 'recover':
    #         checkList = self.__reqObj.getValueList('checked_list')
    #         if len(checkList) == 0:
    #             return self.__returnJsonObject('', 'No task selected.')
    #         #
    #         metaMerger = MetaDataMerger(reqObj=self.__reqObj, entryList=entryList, taskList=checkList, recoverFlag=True,
    #                                     verbose=self.__verbose, log=self.__lfh)
    #         successful_msg = metaMerger.run()
    #     else:
    #         return self.__returnJsonObject('', 'No task was defined!')
    #     #
    #     readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='group_level_config.cif', verbose=self.__verbose, log=self.__lfh)
    #     configDict = readUtil.read()
    #     depictUtil = DepictGroup(reqObj=self.__reqObj, conFigObj=configDict, workFlow=False, verbose=self.__verbose, log=self.__lfh)
    #     taskInfoTxt = depictUtil.getTaskInfo()
    #     if taskInfoTxt == "":
    #         return self.__returnJsonObject(successful_msg, failed_msg)
    #     #
    #     rtrnDict = {}
    #     rtrnDict['textcontent'] = successful_msg
    #     rtrnDict['taskcontent'] = taskInfoTxt
    #     return self.__returnJsonDict(rtrnDict)

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

    def _LaunchEditingPageOp(self):
        """ Launch batch editing page
        """
        if (self.__verbose):
            self.__lfh.write("+WorkManagerWebAppWorker._LaunchEditingPageOp() Starting now\n")
        #
        self.__getSession()
        #
        self.__reqObj.setReturnFormat(return_format="html")
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        #
        myD = {}
        myD['sessionid'] = self.__sessionId
        myD['annotator'] = str(self.__reqObj.getValue('annotator'))
        rC.setHtmlText(self.__processTemplate('editing_tmplt.html', myD))
        #
        return rC

    def _ProcessEditingFormOp(self):
        """ Process batch editing page
        """
        if (self.__verbose):
            self.__lfh.write("+WorkManagerWebAppWorker._ProcessEditingFormOp() Starting now\n")
        #
        self.__getSession()
        #
        dU = DetachUtils(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        mdEditor = MetaDataEditor(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        dU.set(workerObj=mdEditor, workerMethod="ProcessForm")
        dU.runDetach()
        #
        self.__reqObj.setReturnFormat(return_format="json")
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        rC.setStatusCode('running')
        return rC

    def _CheckEditingFormStatusOp(self):
        """ Checking batch editing processing status
        """
        if (self.__verbose):
            self.__lfh.write("+WorkManagerWebAppWorker._CheckEditingFormStatusOp() Starting now\n")
        #
        self.__getSession()
        #
        self.__reqObj.setReturnFormat(return_format="json")
        rC = ResponseContent(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        #
        sph = self.__reqObj.getSemaphore()
        dU = DetachUtils(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
        if (dU.semaphoreExists(sph)):
            mdEditor = MetaDataEditor(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
            rC.addDictionaryItems(mdEditor.GetFormProcessingResult())
        else:
            time.sleep(2)
            rC.setStatusCode('running')
        #
        return rC

    def __returnUpdatePage(self, db):
        """
        """
        readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='level1_config.cif', verbose=self.__verbose, log=self.__lfh)
        configDict = readUtil.read()
        depictUtil = DepictBase(reqObj=self.__reqObj, statusDB=db, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
        _return_page = depictUtil.getPageText(page_id=self.__reqObj.getValue('return_page'))  # noqa: F841
        return self.__returnJsonObject(depictUtil.getPageText(page_id=self.__reqObj.getValue('return_page')), '')

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

    def __refreshTableContent(self, sdb, index, flag):
        """
        """
        readUtil = ReadConFigFile(reqObj=self.__reqObj, configFile='level1_config.cif', verbose=self.__verbose, log=self.__lfh)
        configDict = readUtil.read()
        depContUtil = DepictContent(reqObj=self.__reqObj, statusDB=sdb, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
        returnMap = depContUtil.depictTableContent(index)
        rtrnDict = {}
        if returnMap:
            rtrnDict['status'] = 'OK'
            rtrnDict['map'] = returnMap
            if (index == 'all') and flag:
                if sdb is None:
                    sdb = StatusDbApi(siteId=self.__siteId, verbose=self.__verbose, log=self.__lfh)
                #
                sInfoUtil = ServerInfoUtil(reqObj=self.__reqObj, statusDB=sdb, conFigObj=configDict, verbose=self.__verbose, log=self.__lfh)
                text = sInfoUtil.getServerInfo()
                if text:
                    rtrnDict['serverinfotext'] = text
                #
            #
        else:
            rtrnDict['status'] = 'Failed'
        #
        return self.__returnJsonDict(rtrnDict)

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

    def __getTemplateFile(self):
        """ Get template file for ('sequence', 'other') options
        """
        filePath = ''
        template_identifier = str(self.__reqObj.getValue("template_identifier"))
        if template_identifier:
            version = str(self.__reqObj.getValue("template_file_version"))
            if not version:
                version = 'latest'
            #
            pI = PathInfo(siteId=self.__siteId, sessionPath=self.__sessionPath, verbose=self.__verbose, log=self.__lfh)
            filePath = pI.getFilePath(dataSetId=template_identifier, wfInstanceId=None, contentType='model', formatType='pdbx',
                                      fileSource='archive', versionId=version, partNumber='1')
            #
            if not filePath:
                return '', 'No template file found for Deposition ID=' + template_identifier + ' with version number=' + version + '.'
            #
        else:
            wuu = WebUploadUtils(reqObj=self.__reqObj, verbose=self.__verbose, log=self.__lfh)
            if not wuu.isFileUpload(fileTag='template_file'):
                return '', 'No upload template model file found.'
            #
            uploadFileName = wuu.copyToSession(fileTag='template_file')
            if not os.access(os.path.join(self.__sessionPath, uploadFileName), os.F_OK):
                return '', "Template file '" + os.path.join(self.__sessionPath, uploadFileName) + "' can not be found."
            #
            filePath = os.path.join(self.__sessionPath, 'uploadTemplateFile.cif')
            os.rename(os.path.join(self.__sessionPath, uploadFileName), filePath)
        #
        return filePath, ''

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
