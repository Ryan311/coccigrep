# Copyright (C) 2011 Eric Leblond <eric@regit.org>
#
# You can copy, redistribute or modify this Program under the terms of
# the GNU General Public License version 3 as published by the Free
# Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# version 3 along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

from subprocess import call, Popen, PIPE
from tempfile import NamedTemporaryFile
from os import unlink
from sys import exit

use_pigments = True

try:
    from pygments import highlight
    from pygments.lexers import CLexer
    from pygments.filters import NameHighlightFilter
    from pygments.formatters import Terminal256Formatter, HtmlFormatter
except:
    use_pigments = False

class CocciMatch:
    def __init__(self, mfile, mline, mcol, mlineend, mcolend):
        self.file = mfile
        self.line = int(mline)
        self.column = int(mcol)
        self.lineend = int(mlineend)
        self.columnend = int(mcolend)
    def display(self, stype, mode='raw', oformat='term', before=0, after=0):
        f = open(self.file, 'r')
        lines = f.readlines()
        pmatch = lines[self.line -1][self.column:self.columnend]
        output = ""
        if mode == 'color':
            output += "%s: l.%s -%d, l.%s +%d, %s *%s\n" % (self.file, self.line, before, self.line, after, stype, pmatch)
        for i in range(int(self.line) - 1 - before, int(self.line) + after):
            if mode == 'color':
                output += lines[i]
            elif mode == 'vim':
                output += "%s|%s| (%s *%s): %s" % (self.file, self.line, stype, pmatch, lines[i])
            else:
                output += "%s:%s (%s *%s): %s" % (self.file, self.line, stype, pmatch, lines[i])
        f.close()
        if mode == 'color':
            if use_pigments:
                lexer = CLexer()
                lfilter = NameHighlightFilter(names=[pmatch])
                lexer.add_filter(lfilter)
                if oformat == "term":
                    return highlight(output, lexer, Terminal256Formatter())
                elif oformat == "html":
                    return highlight(output, lexer, HtmlFormatter(noclasses=True))
                else:
                    return output
        return output

class CocciGrep:
    spatch="spatch"
    cocci_smpl = {}
    cocci_smpl['used']="""@init@
typedef %s;
%s *p;
position p1;
@@

p@p1
"""
    cocci_smpl['deref']="""@init@
typedef %s;
%s *p;
position p1;
@@

p@p1->%s
"""
    cocci_smpl['set']="""@init@
typedef %s;
%s *p;
expression E;
position p1;
@@

(
p@p1->%s |= E
|
p@p1->%s = E
|
p@p1->%s += E
|
p@p1->%s -= E
)
"""
    cocci_smpl['test']="""@init@
typedef %s;
%s *p;
expression E;
position p1;
@@

(
p@p1->%s == E
|
p@p1->%s != E
|
p@p1->%s & E
|
p@p1->%s < E
|
p@p1->%s <= E
|
p@p1->%s > E
|
p@p1->%s >= E
|
E == p@p1->%s
|
E != p@p1->%s
|
E & p@p1->%s
|
E < p@p1->%s
|
E <= p@p1->%s
|
E > p@p1->%s
|
E >= p@p1->%s
)
"""
    cocci_python="""

@ script:python @
p1 << init.p1;
@@

for p in p1:
    print "%s:%s:%s:%s:%s" % (p.file,p.line,p.column,p.line_end,p.column_end)
"""

    def __init__(self, stype, attribut, operation):
        self.type = stype
        self.attribut = attribut
        self.operation = operation
        self.verbose = False
    def set_verbose(self):
        self.verbose = True
    def run(self, files):
        # create tmp cocci file:
        tmp_cocci_file = NamedTemporaryFile(suffix=".cocci", delete=False)
        tmp_cocci_file_name = tmp_cocci_file.name

        if self.operation == 'set':
            cocci_grep = CocciGrep.cocci_smpl['set'] % (self.type, self.type, self.attribut, self.attribut, self.attribut, self.attribut) + CocciGrep.cocci_python
        elif self.operation == 'test':
            cocci_grep = CocciGrep.cocci_smpl['test'] % (self.type, self.type, self.attribut, self.attribut, self.attribut, self.attribut, self.attribut, self.attribut, self.attribut,
                                                                     self.attribut, self.attribut, self.attribut, self.attribut, self.attribut, self.attribut, self.attribut) + CocciGrep.cocci_python
        elif self.operation == 'used':
            if self.attribut:
                cocci_grep = CocciGrep.cocci_smpl['deref'] % (self.type, self.type, self.attribut) + CocciGrep.cocci_python
            else:
                cocci_grep = CocciGrep.cocci_smpl['used'] % (self.type, self.type) + CocciGrep.cocci_python
        else:
            raise Exception("unknown method")

        tmp_cocci_file.write(cocci_grep)
        tmp_cocci_file.close()

        # launch spatch
        cmd = [CocciGrep.spatch, "-sp_file", tmp_cocci_file.name] + files

        if self.verbose:
            print "Running: %s." % " ".join(cmd)
            output = Popen(cmd, stdout=PIPE).communicate()[0]
        else:
            output = Popen(cmd, stdout=PIPE, stderr=PIPE).communicate()[0]
        unlink(tmp_cocci_file_name)

        prevfile = None
        prevline = None
        self.matches = []
        for ematch in output.split("\n"):
            try:
                (efile, eline, ecol,elinend, ecolend) = ematch.split(":")
                nmatch = CocciMatch(efile, eline, ecol,elinend, ecolend)
                # if there is equality then we will already display the line
                if (efile == prevfile) and (eline == prevline):
                    continue
                else:
                    prevfile = efile
                    prevline = eline
                    self.matches.append(nmatch)
            except ValueError:
                pass

    def display(self, mode='raw', before=0, after=0, oformat='term'):
        output = ""
        for match in self.matches:
            output += match.display(self.type, mode=mode, oformat=oformat, before=before, after=after)
        return output

