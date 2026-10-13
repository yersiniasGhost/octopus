"""A writable in-memory collection for ingest and repair tests (find, bulk_write of UpdateOne, delete_many)."""


class WritableCollection:
    def __init__(self, docs):
        self.docs = {d['_id']: dict(d) for d in docs}
        self.deleted = []

    def find(self, _filter=None, _projection=None):
        return [dict(d) for d in self.docs.values()]

    def bulk_write(self, ops, ordered=False):
        for op in ops:
            flt, update, upsert = op._filter, op._doc, op._upsert
            match = [d for d in self.docs.values() if all(d.get(k) == v for k, v in flt.items())]
            if match:
                match[0].update(update['$set'])
            elif upsert:
                doc = {**flt, **update['$set']}
                doc.setdefault('_id', f"new{len(self.docs)}")
                self.docs[doc['_id']] = doc

    def delete_many(self, flt):
        for _id in flt['_id']['$in']:
            self.deleted.append(self.docs.pop(_id))


class WritableDB:
    def __init__(self, collections):
        self.collections = {name: WritableCollection(docs) for name, docs in collections.items()}

    def __getitem__(self, name):
        return self.collections[name]

    def list_collection_names(self):
        return list(self.collections)
