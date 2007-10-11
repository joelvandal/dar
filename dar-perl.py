#!/usr/bin/python

### This python scripts automatically generates an RPMforge SPEC file
### for Perl modules based on CPAN information.

### Example modules:
###     perl-Tree-Simple            tests META.yml
###     perl-Tree-Simple-Visitor    tests sub-modules
###     perl-Kwiki                  tests perl Buildrequires epoch

### More documentation about:
###     META.yml    http://module-build.source-forge.net/META-spec-current.html

import sys, os, time, getopt, urllib2, gzip, re, yaml, tarfile, rpm, types
import cElementTree as ElementTree

args = sys.argv[1:]
try:
    logname = os.getlogin()
except:
    logname = 'dag'
debug = False
noarch = True
package_make = False
package_build = False
output = False
realversion = None
authors = []
email = ''
tmppath = '/var/tmp'
license = ''
package_version = None

### Files considered a document:
### Announce ANNOUNCE Artistic ARTISTIC Artistic.txt AUTHORS Bugs BUGS
### Changelog ChangeLog CHANGELOG Changes CHANGES Changes.pod CHANGES.TXT
### Copying COPYING COPYRIGHT Credits CREDITS CREDITS.txt FAQ GNU_GPL.txt
### GNU_LGPL.txt GNU_LICENSE HACKING HISTORY INFO INSTALL INSTALLING
### INSTALL.txt LICENCE LICENSE MANIFEST META.yml NEWS NOTES NOTICE
### PORTING readme README readme.txt README.txt README.TXT RELEASE_NOTES
### SIGNATURE THANKS TODO UPGRADE VERSION *.txt  

docfiles = ('^ANNOUNCE', '^Artistic', '^AUTHORS', '^BUGS', '^ChangeLog',
    '^Changes', '^Changes.pod', '^COPYING', '^COPYRIGHT', '^CREDITS',
    '^FAQ', '^GNU_LICENSE', '^HACKING', '^HISTORY', '^INFO', '^INSTALL',
    '^INSTALLING', '^LICENCE', '^LICENSE', '^MANIFEST', '^META.yml',
    '^NEWS', '^NOTES', '^NOTICE', '^PORTING', '^README', '^RELEASE_NOTES',
    '^ROADMAP', '^SIGNATURE', '^THANKS', '^TODO', '^UPGRADE', '^VERSION',
    '^[^/]+.txt$')

docdirs = ('contrib/', 'doc/', 'docs/', 'eg/', 'example/', 'examples/',
    'htdocs/', 'notes/', 'samples/', 'tutorial/')

authorities = {
    'dag': 'Dag Wieers <dag@wieers.com>',
    'dries': 'Dries Verachtert <dries@ulyssis.org>',
}

licenses = {
    'perl': 'Artistic/GPL',
}

### Add proper epochs to perl-dependencies
epochs = ( '5.0.0', '5.6.1', '5.8.0', '5.8.5', '5.8.8' )

def download(url):
    filename = os.path.join(tmppath, os.path.basename(url))
    try:
        st = os.stat(filename)
        if st and st.st_mtime + 1800 > time.time():
#            print >>sys.stderr, "File %s is recent, skip download." % os.path.basename(url)
            return
    except:
        try:
            req = urllib2.Request(url)
            fdin = urllib2.urlopen(req)
        except:
            return
        fdout = open(filename, 'w')
        fdout.write(fdin.read())
        fdin.close()
        fdout.close()

### FIXME: Create own version comparison instead of using RPM's
def vercmp(v1, v2):
        return rpm.labelCompare((None, v1, None), (None, v2, None))

def epochify(version):
    epoch = 0
    for e, v in enumerate(epochs):
        if vercmp(str(version), v) >= 0:
            epoch = e
    return '%s:%s' % (epoch, version)

try:
    opts, args = getopt.getopt (args, 'adhno:v',
        ['debug', 'help', 'output=', 'version'])
except getopt.error, exc:
    print >>sys.stderr, 'dar-perl: %s, try dar-perl.py -h for a list of all the options' % str(exc)
    sys.exit(1)

for opt, arg in opts:
    if opt in ['-h', '--help']:
        pass
    elif opt in ['-v', '--version']:
        pass
    elif opt in ['-d', '--debug']:
        debug = True
    elif opt in ['-a', '--arch']:
        noarch = False
    elif opt in ['-o', '--output']:
        output = arg

if len(args) < 1:
    print >>sys.stderr, 'Error: You have to provide a package name.'
    sys.exit(1)

package_name = args[0]
package = package_name.replace('::', '-')
modparts = package.split('-')

if len(args) > 1:
    package_version = args[1]

if package.startswith('perl-'):
    modparts = modparts[1:]
    package = '-'.join(modparts)

module = package.replace('-', '::')

### Download latest package list from CPAN
download('ftp://ftp.kulnet.kuleuven.ac.be/pub/mirror/CPAN/modules/02packages.details.txt.gz')

### Download latest authors list from CPAN
download('ftp://ftp.kulnet.kuleuven.ac.be/pub/mirror/CPAN/authors/00whois.xml')

### Find specific package in CPAN package list
modules = []
found = False
fd = gzip.open(os.path.join(tmppath, '02packages.details.txt.gz'), 'r')
for line in fd.readlines():
    pkginfo = line.split()

    ### Skip incorrect lines
    if len(pkginfo) <= 2:
        continue

    pkgmodule = pkginfo[0]
    pkgversion = pkginfo[1]
    pkgpath = pkginfo[2]

    temp = pkgpath.split('/')
    temp = temp[-1].split('-')
    pkgname = '-'.join(temp[0:-1])

    if pkgversion != 'undef' and package == pkgname:
        version = pkgversion
        module = pkgmodule
        module_orig = pkgmodule
        path = pkgpath
        modules.append(pkgmodule)
        found = True
    elif module == pkgmodule:
        print >>sys.stderr, 'Module', module, 'found in package', pkgname
        package = pkgname
        path = pkgpath
        modules.append(module)
        found = True

if not found:
    print >>sys.stderr, 'Error: Module', module, 'or package', package, 'not found in CPAN.'
    sys.exit(1)

modules.sort()

if package_version:
    version = package_version
location = path

#print >>sys.stderr, 'We found package %s with version %s with modules:' % (package, version)
#print >>sys.stderr, pkgmodules

ppath = path.split('/')
mnemo = ppath[2]

### Find specific author in CPAN authors list
tree = ElementTree.ElementTree(file=os.path.join(tmppath, '00whois.xml'))
root = tree.getroot()
for elem in root.getiterator('{http://www.cpan.org/xmlns/whois}cpanid'):
    if mnemo == elem.find('{http://www.cpan.org/xmlns/whois}id').text:
        authorel = elem.find('{http://www.cpan.org/xmlns/whois}fullname')
        emailel = elem.find('{http://www.cpan.org/xmlns/whois}email')
        try:
            author = "%s <%s>" % (authorel.text, emailel.text.replace('@','$').replace('.',','))
        except:
            break

        authors.append(author.encode('utf8', 'replace'))
        break

### Get the correct version from the source distribution
sdistname = "%s-%s.tar.gz" % (package, version)
cdistname = os.path.basename(location)
if not package_version and sdistname != cdistname:
    realversion = version
    ### FIXME: take care of file like Acme-6502-v0.0.6 or something.tgz
    ### Get the version from the cdistname
    m = re.match('[^\d]+([\d\.]+).tar.gz', cdistname)
    if m:
        l = m.groups()
        version = l[0]
    else:
        print >>sys.stderr, 'Warning: Problem retrieving version from %s for package %s.' % (cdistname, package)
#       sys.exit(1)

if realversion == 'undef':
    print >>sys.stderr, 'Error: Version is undefined. Distribution %s is not a package.' % package
    sys.exit(1)
elif realversion == version:
    realversion = None

### Try to download distribution
archive = os.path.join(tmppath, cdistname)
if os.path.isfile(archive):
    os.remove(archive)
source = "http://www.cpan.org/modules/by-module/%s/%s" % (modparts[0], cdistname)
download(source)
if not os.path.isfile(archive):
    source = "http://www.cpan.org/authors/id/%s" % location
    download(source)

### Add %{version} and %{real_version} to source
source = source.replace(version, '%{version}')
if realversion:
    source = source.replace(realversion, '%{real_version}')

### Create basedir out of cdistname
basedir = cdistname.replace('.tar.gz', '')
basedir = basedir.replace(version, '%{version}')
if realversion:
    basedir = basedir.replace(realversion, '%{real_version}')
basedir = basedir.replace(package, '%{real_name}')

### Inspect distribution and extract information (%doc, META.yml, arch/noarch)
distfd = tarfile.open(archive, 'r:gz')
### Remove .tar.gz from base (Name-Version)
base = os.path.basename(archive)
l = base.split('.tar.gz')
base = l[0]
docs = []
docsdirs = []
meta = {}
for file in distfd.getnames():
    ### Remove Name-Version/ from filename
    l = file.split(base+'/')
    if len(l) == 2:
        shortfile = l[1]
    else:
        shortfile = file

    ### Check if this is a noarch or arch package
    if file.endswith('.c') or file.endswith('.h') or file.endswith('.cc') or file.endswith('.xs'):
        noarch = False
        continue

    ### Create %docs filelist
    for docre in docfiles:
        if re.search(docre, shortfile, re.I):
            docs.append(shortfile)
            break

    ### Create %docs directorylist
    if shortfile in docdirs:
        docsdirs.append(shortfile)
        continue

    ### Parse META.yml (http://module-build.source-forge.net/META-spec-current.html)
    if shortfile == 'META.yml':
        member = distfd.getmember(file)
        try:
            meta = yaml.load(distfd.extractfile(member).read())
            if debug:
                print >>sys.stderr, 'Debug: META.yml contains the following info:'
                for key in meta.keys():
                    print >>sys.stderr, '   %s: %s' % (key, meta[key])
        except:
            pass
        continue

    ### Check whether we need to use perl(Module::Build)
    elif shortfile == 'Makefile.PL':
        package_make = True

    elif shortfile == 'Build.PL':
        package_build = True

docs.sort()
docsdirs.sort()

if os.path.isfile(archive):
    os.remove(archive)

### Compare deducted information with META.yml
if meta.has_key('name') and meta['name'] != package:
    print >>sys.stderr, 'Warning: Module %s is part of distribution %s. Please use that instead.' % (package, meta['name'])
#   sys.exit(1)

if meta.has_key('version') and str(meta['version']) != version:
    print >>sys.stderr, 'Warning: Module %s has version mismatch between archive (%s) and META.yml (%s).' % (package, version, meta['version'])

if meta.has_key('type') and meta['type'] != 'module':
    print >>sys.stderr, 'Error: Distribution %s is not a package.' % package
    sys.exit(1)

if meta.has_key('author'):
    authors = []
    if isinstance(meta['author'], types.StringType):
        author = meta['author'].replace('@','$').replace('.',',')
        authors.append(meta['author'].encode('utf8', 'replace'))
    elif isinstance(meta['author'], types.ListType):
        for author in meta['author']:
            author = author.replace('@','$').replace('.',',')
            authors.append(author.encode('utf8', 'replace'))

if meta.has_key('license') and meta['license'] in licenses.keys():
    license = licenses[meta['license']]
else:
    artistic = False
    gpl = False
    lgpl = False
    for doc in docs:
        if doc in ('Artistic', 'ARTISTIC', 'Artistic.txt'):
            artistic = True
        if doc in ('Copying', 'COPYING', 'GNU_GPL.txt', 'GNU_LICENSE'):
            gpl = True
        if doc in ('GNU_LGPL.txt'):
            lgpl = True
    if artistic:
        license = 'Artistic'
    if gpl:
        if license: license = license + '/'
        license = license + 'GPL'
    if lgpl:
        if license: license = license + '/'
        license = license + 'LGPL'
    if not license:
        license = 'Artistic/GPL'
        print >>sys.stderr, 'Warning: License could not be determined.'

### FIXME: Get description from website
if meta.has_key('abstract') and meta['abstract']:
    summary = meta['abstract'].rstrip('.')
    description = meta['abstract'].rstrip('.') + ".\n"
else:
    summary = "Perl module named %s" % package
    description = "perl-%s is a Perl module.\n" % package
    print >>sys.stderr, 'Warning: No abstract found.'

if len(modules) == 1:
    description = description + "\nThis package contains the following Perl module:\n\n    " + module + "\n"
else:
    description = description + "\nThis package contains the following Perl modules:\n\n"
    for module in modules:
        description = description + '    ' + module + "\n"

if meta.has_key('build_requires') and meta['build_requires'] and meta['build_requires'].has_key('perl-Inline'):
    noarch = False
if meta.has_key('requires') and meta['requires'] and meta['requires'].has_key('perl-Inline'):
    noarch = False

if debug:
    print >>sys.stderr, package, version, "perl-%s/perl-%s.spec" % (package, package)
    if noarch:
        print >>sys.stderr, 'noarch package'
    else:
        print >>sys.stderr, 'arch package'
    if realversion:
        print >>sys.stderr, 'source has different version format than CPAN (%s vs %s)' % (version, realversion)
    print >>sys.stderr, 'Found following docs:', ' '.join(docs)
    print >>sys.stderr, 'Distribution archive %s contains:' % cdistname
    for file in distfd.getnames():
        print >>sys.stderr, '  ', file

### See if we have to write a file or write to stdout
if output:
    if os.path.exists(output):
        print >>sys.stderr, 'Error: File %s already exists.' % output
        sys.exit(1)

    outputdir = os.path.dirname(output)
    if outputdir and not os.path.exists(outputdir):
        os.mkdir(outputdir)

    try:
        out = open(output, 'w')
    except:
        print >>sys.stderr, 'Error: Cannot write %s' % output
        sys.exit(1)
else:
    out = sys.stdout

print >>out, '# $Id$'
print >>out, '# Authority:', logname

for author in authors:
    print >>out, "# Upstream: %s" % author
print >>out
print >>out, '%define perl_vendorlib %(eval "`%{__perl} -V:installvendorlib`"; echo $installvendorlib)'
print >>out, '%define perl_vendorarch %(eval "`%{__perl} -V:installvendorarch`"; echo $installvendorarch)'
print >>out
print >>out, '%define real_name', package

if realversion:
    print >>out, '%define real_version', realversion

print >>out

print >>out, "Summary: %s" % summary
print >>out, "Name: perl-%s" % package
print >>out, 'Version:', version
print >>out, 'Release: 1'
print >>out, 'License: %s' % license
print >>out, 'Group: Applications/CPAN'
print >>out, "URL: http://search.cpan.org/dist/%s/" % package
print >>out

print >>out, "Source: %s" % source
print >>out, 'BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root'
print >>out

if noarch:
    print >>out, "BuildArch: noarch"

### FIXME: Add BuildRequires from Makefile.PL ?
if meta.has_key('requires') and meta['requires'] and meta['requires'].has_key('perl'):
    ### FIXME: lstrip 'v' from version if it is a string
    print >>out, "BuildRequires: perl >= %s " % epochify(meta['requires']['perl'])
else:
    print >>out, 'BuildRequires: perl'

if not package_make and package_build:
    print >>out, 'BuildRequires: perl(Module::Build)'

if meta.has_key('build_requires'):
    buildrequires = meta['build_requires'].keys()
    buildrequires.sort()
    for key in buildrequires:
        if meta['build_requires'][key]:
            ### FIXME: lstrip 'v' from version if it is a string
            print >>out, "BuildRequires: perl(%s) >= %s" % (key, meta['build_requires'][key])
        else:
            print >>out, "BuildRequires: perl(%s)" % key

### Requires are extracted by RPM itself
#print "Requires: perl"
#if meta.has_key('requires'):
#   for key in meta['requires']:
#       if meta['requires'][key]:
#           print >>out, "Requires: perl(%s) >= %s" % (key, meta['requires'][key])
#       else:
#           print >>out, "Requires: perl(%s)" % key

if meta.has_key('conflicts'):
    for key in meta['conflicts']:
        print >>out, "Conflict: perl(%s)" % key
print >>out

print >>out, "%description"
print >>out, description

print >>out, "%prep"
print >>out, "%%setup -n %s" % basedir
print >>out

print >>out, "%build"
if noarch:
    if not package_make and package_build:
        print >>out, '%{__perl} Makefile.PL INSTALLDIRS="vendor" destdir="%{buildroot}"'
    else:
        print >>out, '%{__perl} Makefile.PL INSTALLDIRS="vendor" PREFIX="%{buildroot}%{_prefix}"'
    print >>out, '%{__make} %{?_smp_mflags}'
else:
    if not package_make and package_build:
        print >>out, 'CFLAGS="%{optflags}" %{__perl} Makefile.PL INSTALLDIRS="vendor" destdir="%{buildroot}"'
    else:
        print >>out, 'CFLAGS="%{optflags}" %{__perl} Makefile.PL INSTALLDIRS="vendor" PREFIX="%{buildroot}%{_prefix}"'
    print >>out, '%{__make} %{?_smp_mflags} OPTIMIZE="%{optflags}"'
print >>out

print >>out, '%install'
print >>out, '%{__rm} -rf %{buildroot}'
if not package_make and package_build:
    print >>out, '%{__make} install'
else:
    print >>out, '%{__make} pure_install'
print >>out

print >>out, '### Clean up buildroot'
#if noarch:
#   print >>out, '%{__rm} -rf %{buildroot}%{perl_archlib} %{buildroot}%{perl_vendorarch}'
#else:
#   print >>out, '%{__rm} -rf %{buildroot}%{perl_archlib} %{buildroot}%{perl_vendorarch}/auto/*{,/*{,/*}}/.packlist'
print >>out, 'find %{buildroot} -name .packlist -exec %{__rm} {} \;'
print >>out

if docsdirs:
    print >>out, '### Clean up docs'
    print >>out, 'find', ' '.join(docsdirs), '-type f -exec %{__chmod} a-x {} \;'
    print >>out

print >>out, '%clean'
print >>out, '%{__rm} -rf %{buildroot}'
print >>out

### FIXME: Create %files list based on test-build or source-tree ?
print >>out, '%files'
print >>out, '%defattr(-, root, root, 0755)'
### Check DOCS in archive from "grep -h '^%doc' /dar/rpms/perl*/perl*.spec | grep -v mandir | xargs -n 1 | sort | uniq"
if not docsdirs:
    print >>out, '%doc', ' '.join(docs)
else:
    print >>out, '%doc', ' '.join(docs), ' '.join(docsdirs)

if len(modules) > 4:
    print >>out, '%doc %{_mandir}/man3/*.3pm*'
else:
    for module in modules:
        print >>out, "%%doc %%{_mandir}/man3/%s.3pm*" % module

### FIXME: Use modules and module_orig to create %files list
if noarch:
    ### Print directory entries (if any)
    if modparts[:-1]:
        str = '%dir %{perl_vendorlib}/'
        for nr, part in enumerate(modparts[:-1]):
            str = str + "%s/" % modparts[nr]
            print >>out, str

    ### Print module directory
    str = '#%{perl_vendorlib}/'
    for nr, part in enumerate(modparts):
        str = str + "%s/" % modparts[nr]
    print >>out, str

    ### Print module
    if modparts[:-1]:
        str = '%{perl_vendorlib}/'
        for nr, part in enumerate(modparts[:-1]):
            str = str + "%s/" % modparts[nr]
        print >>out, str + "%s.pm" % modparts[-1]
    else:
        print >>out, '%%{perl_vendorlib}/%s.pm' % modparts[0]
else:
    ### Print directory entries (if any)
    if modparts[:-1]:
        str = '%dir %{perl_vendorarch}/'
        for nr, part in enumerate(modparts[:-1]):
            str = str + "%s/" % modparts[nr]
            print >>out, str

    ### Print module directory
    str = '%{perl_vendorarch}/'
    for nr, part in enumerate(modparts[:-1]):
        str = str + "%s/" % modparts[nr]
    print >>out, str + "%s.pm" % modparts[-1]

    ### Print auto directory entries (if any)
    if modparts[:-1]:
        str = '%dir %{perl_vendorarch}/auto/'
        for nr, part in enumerate(modparts[:-1]):
            str = str + "%s/" % modparts[nr]
            print >>out, str

    ### Print auto module directory
    str = '%{perl_vendorarch}/auto/'
    for nr, part in enumerate(modparts):
        str = str + "%s/" % modparts[nr]
    print >>out, str

print >>out

print >>out, '%changelog'
print >>out, '* %s %s - %s-1' % (time.strftime('%a %b %d %Y', time.localtime()), authorities[logname], version)
print >>out, '- Initial package. (using DAR)'

if output:
    out.close()

sys.exit(0)
