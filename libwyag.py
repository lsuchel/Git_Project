import argparse
import collections
import configparser
from datetime import datetime
import  grp,pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

argparse = argparse.ArgumentParser(description="No idea what I am doing")
argsubparsers = argparse.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

def main(argv=sys.argv[1:]):
    args = argparse.parse_args(argv)
    match args.command:
        case 'add'          : cmd_add(args)
        case 'cat-file'     : cmd_cat_file(args)
        case 'check-ignore' : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_files(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Bad command.")

class GitRepository (object):
    """Git Repo"""

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception("Not Git Rep %s" % path)
        
        # Read config file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("config file missing")
        
        if not force:
            vers = int(self.conf.get("core", "repoformatversion"))
            if vers != 0:
                raise Exception("unsupported repoformatversion %s" % vers)
def repo_path(repo, *path):
    """Compute path under repo's gitdir."""
    return os.path.join(repo.gitdir, *path)
def repo_file(repo, *path, mkdir=False):
    """Same as repo_path, but create dirname(*path) if absent.  For
example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create
.git/refs/remotes/origin."""

    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
    """Same as repo_path, but mkdir *path if absent if mkdir."""

    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception ("Not a directory %s" % path)
        
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    
def repo_create(path):
    """Create a new repository at path."""

    repo = GitRepository(path, True)

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception ("%s is not a directory!" % path)
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception("%s is not empty!" % path)
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo,"objects", mkdir=True)
    assert repo_dir(repo,"refs", "tags", mkdir=True)
    assert repo_dir(repo,"refs", "heads", mkdir=True)

    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo

def repo_default_config():
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret

argsp = argsubparsers.add_parser("init", help="Intialize a new and empty repository.")

argsp.add_argument("path",
                   metavar="directory",
                   nargs="?",
                   default=".",
                   help="Where to create the repository.")


def cmd_init(args):
    repo_create(args.path)

def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)
    
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        if required:
            raise Exception("No git directory.")
        else:
            return None
        
    return repo_find(parent, required)

class GitObject (object):

    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self, repo):
        """This function MUST be implemented by subclasses.
        It must read the object's contents from self.data, a byte string, and do whatever
        it takes to convert it into a meaningful representation. What exactly that means
        depends on each subclass."""
        raise Exception("unimplemented")
    
    def deserialize(self, data):
        raise Exception("Unimplemented")
    
    def init(self):
        pass

def object_read(repo, sha):
    """Read object sha from Git repo. Return a GitObject whose type depends on the object."""

    path = repo_file(repo, "objects", sha[0:2], sha[2:])
    if not os.path.isfile(path):
        return None
    
    with open (path, "rb") as f:
        raw =zlib.decompress(f.read())
        x = raw.find (b' ')
        fmt = raw[0:x]

        y = raw.find(b'\x00',x)
        size = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception("Malformed object {0}: bad length". format(sha))
        
    match fmt:
        case b'commit' : c=GitCommit
        case b'tree'   : c=GitTree
        case b'tag'    : c=GitTag
        case b'blob'   : c=GitBlob
        case _:
            raise Exception("nknown type {0} for object {1}".format(fmt.decode("ascii"), sha))
        
    return c(raw[y+1:])

def object_wirte(obj, repo=None):
    data = obj.serialize()
    result = obj.fmt + b' '+str(len(data)).encode() + b'\x00' + data
    sha = hashlib.shal(result).hexdigest()

    if repo:
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                f.write(zlib.compress(result))
    return sha

class GitBlob(GitObject):
    fmt=b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

argsp = argsubparsers.add_parser("cat-file", help="Provide content of rep objs.")

argsp.add_argument("type", metavar="type", choices=["blob", "commit", "tag", "tree"], help="Specify the type")

argsp.add_argument("object", metavar="object", help="The object to display")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())

def object_find(repo, name, fmt=None, follow=True):
    return name

argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute object ID and optionally creates a blob from a file")

argsp.add_argument("-t",
                    metavar="type",
                    dest="type",
                    choices=["blob","commit","tag","tree"],
                    default="Specify the type")

argsp.add_argument("-w",
                    dest="write",
                    action="store_true",
                    help="Actually write the object into database")

argsp.add_argument("path",
                    help="Read object from <file>")

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None

    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

def object_hash(fd, fmt, repo=None):
    """Hash object, writing it to repo if provided."""
    data = fd.read()

    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree'   : obj=GitTree(data)
        case b'tag'    : obj=GitTag(data)
        case b'blob'   : obj=GitBlob(data)
        case _: raise Exception("Unknown type %s!" % fmt)

    return object_write(obj, repo)

def keyv_parse(raw, start=0, dct=None):
    if not dct:
        dct = collections.OrderedDict()

    spce = raw.find(b' ', start)
    neli = raw.find(b'\n', start)
    if (spce < 0) or (neli < spce):
        assert neli == start
        dct[None] = raw[start+1:]
        return dct

    key = raw[start:spce]

    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break

    value = raw[spce+1:end].replace(b'\n', b'\n')
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]
    else:
        dct[key] = value
    
    return keyv_parse(raw, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
    ret = b''

    for k in kvlm.keys():
        if k == None: continue
        val = kvlm[k]
        if type(val) != list:
            val = [ val ]
        
        for v in val:
            ret += k + b' ' + (v.replcae(b'\n',b'\n '))+ b'\n'

    ret += b'\n' +kvlm[None] + b'\n'

    return ret

class GitCommit(GitObject):
    fmt = b'commit'

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)

    def init(self):
        self.kvlm = dict()

argsp = argsubparsers.add_parser("log", help = "Display history of commit that was given.")
argsp.add_argument("commit",
                   default="HEAD",
                   nargs="?",
                   help="Commit to start at.")

def cmd_log(args):
    repo = repo_find()

    print("digraph wyaglog{")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def log_graphviz(repo, sha, seen):

    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo, sha)
    short_hash = sha[0:8]
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\","\\\\")
    message = message.replace("\"","\\\"")

    if "\n" in message:
        message = message[:message.index("\n")]

    print ("  c_{0} [label=\"{1}: {2}\"]".format(sha, sha[0:7], message))
    assert commit.fmt==b'commit'

    if not b'parent' in commit.kvlm.keys():
        return

    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")
        print("  c_{0} -> c{1};".format(sha, p))
        log_graphviz(repo, p, seen)

class GitTreeLeaf (object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_parse_one(ra, start=0):
    x= raw.find(b' ',start)
    assert x-start == 5 or x-start==6

    mode = raw[start:x]
    if len(mode) == 5:
        mode =b" " + mode

    y = raw.find(b'\x00'. x)
    path = raw[x+1:y]

    sha = format(int.from_bytes(raw[y+1:y+21], "big"), "040x")
    return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(rasw, pos)
        ret.append(data)

    return ret

def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b"10"):
        return leaf.path
    else:
        return leaf.path + "/"

def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")
    return ret

class GitTree(GitObject):
    fmt=b'tree'

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)

    def init(self):
        self.items = list()

argsp = argsubparsers.add_parser("ls-tree", help="Pretty-print a tree object.")
argsp.add_argument("-r",
                   dest="recursive",
                   action="store_true",
                   help="Recurse into sub-trees")

argsp.add_argument("tree",
                   help="A tree-ish object.")

def cmd_ls_tree(args):
    repo = repo_fin()
    ls_tree(repo, args.tree, args.recursive)

def ls_tree(repo, ref, recursive=None, prefix=""):
    sha = object_find(repo, ref, fmt=b"tree")
    obj = object_read(repo, sha)
    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]

        match type:
            case b'04': type = "tree"
            case b'10': type = "blob"
            case b'12': type = "blob"
            case b'16': type = "commit"
            case _: raise Exception("Weird tree leaf mode {}".format(item.mode))

        if not (recursive and type =='tree'):
            print("{0} {1} {2}\t{3}".format(
                "0" * (6- len(item.mode)) +item.mode.decode("ascii"),
                type,
                item.sha,
                os.path.join(prefix, item.path)))
        else:
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

rgsp = argsubparsers.add_parser("checkout", help = "checkout a commit inside directory.")

argsp.add_argument("commit",
                   help = "The commit or tree to checkout.")

argsp.add_argument("path",
                   help = "The EMPTY directory to checkout on.")

def cmd_checkout(args):
    repo = repo_find()

    obj = object_read(repo, object_find(repo, args.commit))

    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception("Not a directory {0}!".format(args.path))
        if os.listdir(args.path):
            raise Exception("Not empty {0}!".format(args.path))
    else:
        os.makedirs(args.path)

    tree_checkout(repo, obj, os.path.realpath(args.path))

def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)

def ref_resolve(repo, ref):
    path = repo_file(repo, ref)

    if not os.path.isfile(path):
        return None

    with open(path, 'r')as fp:
        data = fp.read()[:-1]

    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    else:
        return data

def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    ret = collections.OrderdDict()
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)
        else:
            ret[f] = ref_resolve(repo, can)

    return ret

argsp = argsubparsers.add_parser("show-ref", help="List references.")

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
    for k, v in refs.items():
        if type(v) == str:
            print ("{0}{1}{2}".format(
                v + " " if with_hash else "",
                prefix + "/" if prefix else "",
            k))
        else:
            show_ref(repo, v, with_hash=with_hash, prefix="{0}{1}{2}".format(prefix, "/" if prefix else "", k))

class GitTag(GitCommit):
    fmt = b'tag'

argsp = argsubparsers.add_parser(
    "tag",
    help="List and create tags")

argsp.add_argument("-a",
                   action="store_true",
                   dest="create_tag_object",
                   help="possible to create a tag object")

argsp.add_argument("name",
                   nargs="?",
                   help="The new tag's name")

argsp.add_argument("object",
                   default="HEAD",
                   nargs="?",
                   help="object - the new tag will point to")

def cmd_tag(args):
    repo = repo_find()

    if args.name:
        tag_create(repo,
                   args.name,
                   args.object,
                   type="object" if args.create_tag_object else "ref")
    else:
        refs = ref_list(repo)
        show_ref(repo, refs["tags"], with_hash=False)

def tag_create(repo, name, ref, create_tag_object=False):
    sha = object_find(repo, ref)

    if create_tag_object:
        tag = GitTag(repo)
        tag.kvlm = collections.OrderedDict()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        tag.kvlm[b'tagger'] = b'Wyag <example@example.com>'
        tag.kvlm[None] = b"A tag created by Wyag, which won't let you customize the message!"
        tag_sha = object_write(tag)
        ref_create(repo, "tags/" + name, tag_sha)
    else:
        ref_create(repo, "tags/" + name, sha)

def ref_create(repo, ref_name, sha):
    with open(repo_file(repo, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")

def object_resolve(repo, name):
    """Resolve name to an object hash in repo.

This function is aware of:

 - the HEAD literal
    - short and long hashes 
    - tags
    - branches
    - remote branches """
    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    if not name.strip():
        return None
    
    if name =="HEAD":
        return [ ref_resolve(repo, "HEAD") ]
    
    if hashRE.match(name):
        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "objects", prefix, mkdir=False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    candidates.append(prefix + f)

    as_tag = ref_resolve(repo, "refs/tags/" + name)
    if as_tag:
        candidates.append(as_tag)

    as_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_branch:
        candidates.append(as_branch)

    return candidates

def object_find(repo, name, fmt=None, follow=True):
    sha = object_resolve(repo, name)

    if not sha:
        raise Exception("No such reference {0}.".format(name))
    
    sha = sha[0]

    if not fmt:
        return sha
    
    while True:
        obj = object_read(repo, sha)

        if obj.fmt == fmt:
            return sha
        
        if not follow:
            return None
        
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")
        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")
        else:
            return None
        
argsp = argsubparsers.add_parser(
    "rev-parse",
    help="Parse revision (or other objects) identifiers")

argsp.add_argument("--wyag-type",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default=None,
                   help="Specify the expected type")

argsp.add_argument("name",
                   help="The name to parse")

def cmd_rev_parse(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None

    repo = repo_find()

    print (object_find(repo, args.name, fmt, follow=True))

class GitIndexEntry (object):
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None, mode_type=None, mode_perms=None, uid=None, gid=None, fsize=None, sha=None, flag_assume_valid=None, flag_stage=None, name=None):
        self.ctime = ctime
        self.mtime = mtime
        self.dev = dev
        self.ino = ino
        self.mode_type = mode_type
        self.mode_perms = mode_perms
        self.uid = uid
        self.gid = gid
        self.fsize = fsize
        self.sha = sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        self.name = name

class GitIndex (object):
    version = None
    entries = []

    def __init__(self, version=2, entries=None):
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries

def index_read(repo):
    index_file = repo_file(repo, "index")

    if not os.path.exists(index_file):
        return GitIndex()
    
    with open(index_file, 'rb') as f:
        raw = f.read()

    header = raw[:12]
    signature = header[:4]
    assert signature == b"DIRC"
    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "wyag only supports index file version 2"
    count = int.from_bytes(header[8:12], "big")

    entries = list()

    content = raw[12:]
    idx = 0
    for i in rang(0, count):
        ctime_s = int.from_bytes(content[idx: idx+4], "big")
        ctime_ns = int.from_bytes(content[idx+4: idx+8], "big")
        mtime_s = int.from_bytes(content[idx+8: idx+12], "big")
        mtime_ns = int.from_bytes(content[idx+12: idx+16], "big")
        dev = int.from_bytes(content[idx+16: idx+20], "big")
        ino = int.from_bytes(content[idx+20: idx+24], "big")
        unused = int.from_bytes(content[idx+24: idx+26], "big")
        assert 0 == unused
        mode = int.from_bytes(content[idx+26: idx+28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]
        mode_perms = mode & 0b0000000111111111
        uid = int.from_bytes(content[idx+28: idx+32], "big")
        gid = int.from_bytes(content[idx+32: idx+36], "big")
        fsize = int.from_bytes(content[idx+36: idx+40], "big")
        sha = format(int.from_bytes(content[idx+40: idx+60], "big"), "040x")
        flags = int.from_bytes(content[idx+60: idx+62], "big")
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage =  flags & 0b0011000000000000
        name_length = flags & 0b0000111111111111

        idx += 62

        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x000
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1
        else:
            print("Notice: Name is 0x{:X} bytes long.".format(name_length))
            null_idx = content.find(b'\x00', idx + 0xFFF)
            raw_name = content[idx: null_idx]
            idx = null_idx + 1

        name = raw_name.decode("utf8")

        idx = 8 * ceil(idx / 8)

        entries.append(GitIndexEntry(ctime=(ctime_s, ctime_ns),
                                     mtime=(mtime_s,  mtime_ns),
                                     dev=dev,
                                     ino=ino,
                                     mode_type=mode_type,
                                     mode_perms=mode_perms,
                                     uid=uid,
                                     gid=gid,
                                     fsize=fsize,
                                     sha=sha,
                                     flag_assume_valid=flag_assume_valid,
                                     flag_stage=flag_stage,
                                     name=name))
        
    return GitIndex(version=version, entries=entries)

argsp = argsubparsers.add_parser("ls-files", help = "List all the stage files")
argsp.add_argument("--verbose", action="store_true", help="Show everything.")

def cmd_ls_files(args):
  repo = repo_find()
  index = index_read(repo)
  if args.verbose:
    print("Index file format v{}, containing {} entries.".format(index.version, len(index.entries)))

  for e in index.entries:
    print(e.name)
    if args.verbose:
      print("  {} with perms: {:o}".format(
        { 0b1000: "regular file",
          0b1010: "symlink",
          0b1110: "git link" }[e.mode_type],
        e.mode_perms))
      print("  on blob: {}".format(e.sha))
      print("  created: {}.{}, modified: {}.{}".format(
        datetime.fromtimestamp(e.ctime[0])
        , e.ctime[1]
        , datetime.fromtimestamp(e.mtime[0])
        , e.mtime[1]))
      print("  device: {}, inode: {}".format(e.dev, e.ino))
      print("  user: {} ({})  group: {} ({})".format(
        pwd.getpwuid(e.uid).pw_name,
        e.uid,
        grp.getgrgid(e.gid).gr_name,
        e.gid))
      print("  flags: stage={} assume_valid={}".format(
        e.flag_stage,
        e.flag_assume_valid))

argsp = argsubparsers.add_parser("check-ignore", help = "Check path(s) against ignore rules.")
argsp.add_argument("path", nargs="+", help="Paths to check")

def cmd_check_ignore(args):
    repo = repo_find()
    rules = gitignore_read(repo)
    for path in args.path:
        if check_ignore(rules, path):
            print(path)

def gitignore_parsel(raw):
    raw = raw.strip()

    if not raw or raw[0] == "#":
        return None
    elif raw[0] == "!":
        return (raw[1:], False)
    elif raw[0] == "\\":
        return (raw[1:], True)
    else:
        return (raw, True)
    
def gitignore_parse(lines):
    ret = list()

    for line in lines:
        parsed = gitignore_parsel(lines)
        if parsed:
            ret.append(parsed)

    return ret

class GitIgnore(object):
    absolute = None
    scoped = None

    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped

def gitignore_read(repo):
    ret = GitIgnore(absolute=list(), scoped=dict())

    repo_file = os.path.join(repo.gitdir, "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_COFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home, "git/ignore")

    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    index = index_read(repo)

    for entry in  index.entries:
        if entry.name == ".gitignore" or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = gitignore_parse(lines)
    return ret

def check_ignorel(rules, path):
    result = None
    for (pattern, value) in rules:
        if fnmatch(path, pattern):
            result = value
    return result

def check_ignore_scoped(rules, path):
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignorel(rules[parent], path)
            if result != None:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)
    return None

def check_ignore_absolute(rules, path):
    parent = os.path.dirname(path)
    for ruleset in rules:
        result = check_ignorel(ruleset, path)
        if result != None:
            return result
    return False

def check_ignore(rules, path):
    if os.isabs(path):
        raise Exception("This requires path to be root in repository")
    
    result = check_ignore_scoped(rules.scoped, path)
    if result != None:
        return result
    
    return check_ignore_absolute(rules.absolute, path)

argsp = argsubparsers.add_parser("status", help = "Show the working tree status.")

def cmd_status(_):
    repo = repo_find()
    index = index_read(repo)

    cmd_status_branch(repo)
    cmd_status_head_index(repo, index)
    print()
    cmd_status_index_worktree(repo, index)

def branch_get_active(repo):
    with open(repo_file(repo, "HEAD"), "r") as f:
        head = f.read()

    if head.startswith("ref: refs/heads/"):
        return(head[16:-1])
    else:
        return False
    
def cmd_status_branch(repo):
    branch = branch_get_active(repo)
    if branch:
        print("On branch {}.".format(branch))
    else:
        print("HEAD detached at {}.".format (object_find(repo, "HEAD")))

def tree_to_dict(repo, ref, prefix=""):
    ret = dict()
    tree_sha = object_find(repo, ref, fmt=b"tree")
    tree = object_read(repo, tree_sha)

    for leaf in tree.items:
        full_path = os.path.join(prefix, leaf.path)

        is_subtree = leaf.mode.startswith(b'04')

        if is_subtree:
            ret.update(tree_to_dict(repo, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha

    return ret

def cmd_status_head_index(repo, index):
    print("Changes to be committed:")

    head = tree_to_dict(repo, "HEAD")
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                print("  modified:", entry.name)
            del head[entry.name]
        else:
            print("  added:  ", entry.name)

    for entry in head.keys():
        print("  deleted: ", entry)

def cmd_status_index_worktree(repo, index):
    print("Changes not staged for commit:")

    ignore = gitignore_read(repo)

    gitdir_prefix = repo.gitdir + os.path.sep

    all_files = list()

    for (root, _, files) in os.walk(repo.worktree, True):
        if root==repo.gitdir or root.startswith(gitdir_prefix):
            continue
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, repo.worktree)
            all_files.append(rel_path)

    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)

        if not os.path.exists(full_path):
            print("  deleted: ", entry.name)
        else:
            stat = os.stat(full_path)

            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                with open(full_path, "rb") as fd:
                    new_sha = object_hash(fd, b"blob", None)
                    same = entry.sha == new_sha

                    if not same:
                        print("  modified:", entry.name)

        if entry.name in all_files:
            all_files.remove(entry.name)

    print()
    print("Untracked files:")

    for f in all_files:
        if not check_ignore(ignore, f):
            print(" ", f)

