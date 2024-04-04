from abc import ABCMeta, abstractmethod


class BaseImporter:
    __metaclass__ = ABCMeta

    @abstractmethod
    def import_data(self, data):
        raise NotImplementedError()

    @property
    @abstractmethod
    def importer_name(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def importer_help(self):
        raise NotImplementedError()
