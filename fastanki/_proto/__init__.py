"Anki's protobuf messages, loaded from vendored serialized descriptors into a private pool, so the `anki` wheel can coexist at any version"
import importlib
from pathlib import Path
from types import SimpleNamespace
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

_blob = Path(__file__).parent/'descriptors.binpb'
_pool = descriptor_pool.DescriptorPool()
for _f in descriptor_pb2.FileDescriptorSet.FromString(_blob.read_bytes()).file: _pool.Add(_f)

def _mod(fname): return SimpleNamespace(**{k:message_factory.GetMessageClass(v)
    for k,v in _pool.FindFileByName(fname).message_types_by_name.items()})

notetypes_pb2,decks_pb2,deck_config_pb2 = map(_mod, ['anki/notetypes.proto','anki/decks.proto','anki/deck_config.proto'])

def refresh():
    "Re-dump `descriptors.binpb` from the protos of the installed `anki` wheel, returning the proto file names written"
    files,seen = [],set()
    def add(fd):
        if fd.name in seen: return
        seen.add(fd.name)
        for d in fd.dependencies: add(d)
        files.append(descriptor_pb2.FileDescriptorProto.FromString(fd.serialized_pb))
    for r in 'notetypes','decks','deck_config': add(importlib.import_module(f'anki.{r}_pb2').DESCRIPTOR)
    _blob.write_bytes(descriptor_pb2.FileDescriptorSet(file=files).SerializeToString())
    return [f.name for f in files]
