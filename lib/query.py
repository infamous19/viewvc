#!/usr/bin/python
# -*- Mode: python -*-
#
# Copyright (C) 2000 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://www.lyra.org/viewcvs/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://www.lyra.org/viewcvs/
#
# -----------------------------------------------------------------------
#
# CGI script to process and display queries to CVSdb
#
# This script is part of the ViewCVS package. More information can be
# found at http://www.lyra.org/viewcvs/.
#
# -----------------------------------------------------------------------
#

#########################################################################
#
# INSTALL-TIME CONFIGURATION
#
# These values will be set during the installation process. During
# development, they will remain None.
#

CONF_PATHNAME = None

#########################################################################

import os
import sys
import string
import time

import cvsdb
import viewcvs
import ezt
import debug
import urllib

class FormData:
    def __init__(self, form):
        self.valid = 0
        
        self.repository = ""
        self.branch = ""
        self.directory = ""
        self.file = ""
        self.who = ""
        self.sortby = ""
        self.date = ""
        self.hours = 0

        self.decode_thyself(form)
        
    def decode_thyself(self, form):
        try:
            self.repository = string.strip(form["repository"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
        
        try:
            self.branch = string.strip(form["branch"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.directory = string.strip(form["directory"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.file = string.strip(form["file"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.who = string.strip(form["who"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        else:
            self.valid = 1
            
        try:
            self.sortby = string.strip(form["sortby"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        
        try:
            self.date = string.strip(form["date"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        
        try:
            self.hours = int(form["hours"].value)
        except KeyError:
            pass
        except TypeError:
            pass
        except ValueError:
            pass
        else:
            self.valid = 1
        
## returns a tuple-list (mod-str, string)
def listparse_string(str):
    return_list = []

    cmd = ""
    temp = ""
    escaped = 0
    state = "eat leading whitespace"

    for c in str:
        ## handle escaped charactors
        if not escaped and c == "\\":
            escaped = 1
            continue

        ## strip leading white space
        if state == "eat leading whitespace":
            if c in string.whitespace:
                continue
            else:
                state = "get command or data"

        ## parse to '"' or ","
        if state == "get command or data":

            ## just add escaped charactors
            if escaped:
                escaped = 0
                temp = temp + c
                continue

            ## the data is in quotes after the command
            elif c == "\"":
                cmd = temp
                temp = ""
                state = "get quoted data"
                continue

            ## this tells us there was no quoted data, therefore no
            ## command; add the command and start over
            elif c == ",":
                ## strip ending whitespace on un-quoted data
                temp = string.rstrip(temp)
                return_list.append( ("", temp) )
                temp = ""
                state = "eat leading whitespace"
                continue

            ## record the data
            else:
                temp = temp + c
                continue
                
        ## parse until ending '"'
        if state == "get quoted data":
            
            ## just add escaped charactors
            if escaped:
                escaped = 0
                temp = temp + c
                continue

            ## look for ending '"'
            elif c == "\"":
                return_list.append( (cmd, temp) )
                cmd = ""
                temp = ""
                state = "eat comma after quotes"
                continue

            ## record the data
            else:
                temp = temp + c
                continue

        ## parse until ","
        if state == "eat comma after quotes":
            if c in string.whitespace:
                continue

            elif c == ",":
                state = "eat leading whitespace"
                continue

            else:
                print "format error"
                sys.exit(1)

    if cmd or temp:
        return_list.append((cmd, temp))

    return return_list

def decode_command(cmd):
    if cmd == "r":
        return "regex"
    elif cmd == "l":
        return "like"
    else:
        return "exact"

def form_to_cvsdb_query(form_data):
    query = cvsdb.CreateCheckinQuery()

    if form_data.repository:
        for cmd, str in listparse_string(form_data.repository):
            cmd = decode_command(cmd)
            query.SetRepository(str, cmd)
        
    if form_data.branch:
        for cmd, str in listparse_string(form_data.branch):
            cmd = decode_command(cmd)
            query.SetBranch(str, cmd)
        
    if form_data.directory:
        for cmd, str in listparse_string(form_data.directory):
            cmd = decode_command(cmd)
            query.SetDirectory(str, cmd)

    if form_data.file:
        for cmd, str in listparse_string(form_data.file):
            cmd = decode_command(cmd)
            query.SetFile(str, cmd)

    if form_data.who:
        for cmd, str in listparse_string(form_data.who):
            cmd = decode_command(cmd)
            query.SetAuthor(str, cmd)

    if form_data.sortby == "author":
        query.SetSortMethod("author")
    elif form_data.sortby == "file":
        query.SetSortMethod("file")
    else:
        query.SetSortMethod("date")

    if form_data.date:
        if form_data.date == "hours" and form_data.hours:
            query.SetFromDateHoursAgo(form_data.hours)
        elif form_data.date == "day":
            query.SetFromDateDaysAgo(1)
        elif form_data.date == "week":
            query.SetFromDateDaysAgo(7)
        elif form_data.date == "month":
            query.SetFromDateDaysAgo(31)
            
    return query

def prev_rev(rev):
    '''Returns a string representing the previous revision of the argument.'''
    r = string.split(rev, '.')
    # decrement final revision component
    r[-1] = str(int(r[-1]) - 1)
    # prune if we pass the beginning of the branch
    if len(r) > 2 and r[-1] == '0':
        r = r[:-2]
    return string.join(r, '.')

def build_commit(server, desc, files, cvsroots, viewcvs_link):
    ob = _item(num_files=len(files), files=[])
    
    if desc:
        ob.desc = string.replace(server.escape(desc), '\n', '<br>')
    else:
        ob.desc = '&nbsp;'

    for commit in files:
        ctime = commit.GetTime()
        if not ctime:
            ctime = "&nbsp;"
        else:
          if (cfg.options.use_localtime):
            ctime = time.strftime("%y/%m/%d %H:%M %Z", time.localtime(ctime))
          else:
            ctime = time.strftime("%y/%m/%d %H:%M", time.gmtime(ctime)) \
                  + ' UTC'
        
        ## make the file link
        file = os.path.join(commit.GetDirectory(), commit.GetFile())
        file_full_path = os.path.join(commit.GetRepository(), file)
        file = string.replace(file, os.sep, '/')

        ## if we couldn't find the cvsroot path configured in the 
        ## viewcvs.conf file, then don't make the link
        try:
          cvsroot_name = cvsroots[commit.GetRepository()]
        except KeyError:
          cvsroot_name = None
        
        if cvsroot_name:
            flink = '[%s] <a href="%s/%s?root=%s">%s</a>' % (
                    cvsroot_name, viewcvs_link, urllib.quote(file),
                    cvsroot_name, file)
            if commit.GetType() == commit.CHANGE:
                dlink = '%s/%s?root=%s&amp;view=diff&amp;r1=%s&amp;r2=%s' % (
                    viewcvs_link, urllib.quote(file), cvsroot_name,
                    prev_rev(commit.GetRevision()), commit.GetRevision())
            else:
                dlink = None
        else:
            flink = file_full_path
            dlink = None

        ob.files.append(_item(date=ctime,
                              author=commit.GetAuthor(),
                              link=flink,
                              rev=commit.GetRevision(),
                              branch=commit.GetBranch(),
                              plus=int(commit.GetPlusCount()),
                              minus=int(commit.GetMinusCount()),
                              type=commit.GetTypeString(),
                              difflink=dlink,
                              ))

    return ob

def run_query(server, form_data, viewcvs_link):
    query = form_to_cvsdb_query(form_data)
    db = cvsdb.ConnectDatabaseReadOnly()
    db.RunQuery(query)

    if not query.commit_list:
        return [ ]

    commits = [ ]
    files = [ ]

    cvsroots = {}
    rootitems = cfg.general.cvs_roots.items() + cfg.general.svn_roots.items()
    for key, value in rootitems:
        value = os.path.normcase(value)
        while value[-1] == os.sep:
            value = value[:-1]
        cvsroots[value] = key

    current_desc = query.commit_list[0].GetDescription()
    for commit in query.commit_list:
        desc = commit.GetDescription()
        if current_desc == desc:
            files.append(commit)
            continue

        commits.append(build_commit(server, current_desc, files, cvsroots, viewcvs_link))

        files = [ commit ]
        current_desc = desc

    ## add the last file group to the commit list
    commits.append(build_commit(server, current_desc, files, cvsroots, viewcvs_link))

    return commits

def handle_config():
    viewcvs.handle_config()
    global cfg
    cfg = viewcvs.cfg

def main(server, viewcvs_link):
  try:
    handle_config()

    form = server.FieldStorage()
    form_data = FormData(form)

    if form_data.valid:
        commits = run_query(server, form_data, viewcvs_link)
        query = None
    else:
        commits = [ ]
        query = 'skipped'

    script_name = server.getenv('SCRIPT_NAME', '')

    data = {
      'cfg' : cfg,
      'address' : cfg.general.address,
      'vsn' : viewcvs.__version__,

      'repository' : server.escape(form_data.repository, 1),
      'branch' : server.escape(form_data.branch, 1),
      'directory' : server.escape(form_data.directory, 1),
      'file' : server.escape(form_data.file, 1),
      'who' : server.escape(form_data.who, 1),
      'docroot' : cfg.options.docroot is None \
                  and viewcvs_link + '/' + viewcvs.docroot_magic_path \
                  or cfg.options.docroot,

      'sortby' : form_data.sortby,
      'date' : form_data.date,

      'query' : query,
      'commits' : commits,
      'num_commits' : len(commits),
      }

    if form_data.hours:
      data['hours'] = form_data.hours
    else:
      data['hours'] = 2

    template = ezt.Template()
    template.parse_file(os.path.join(viewcvs.g_install_dir,
                                     cfg.templates.query))

    server.header()

    # generate the page
    template.generate(sys.stdout, data)

  except SystemExit, e:
    pass
  except:
    debug.PrintException(server, debug.GetExceptionData())

class _item:
  def __init__(self, **kw):
    vars(self).update(kw)
