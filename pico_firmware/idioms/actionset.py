class ActionSet(list):
    def __init__(self, *args):
        super().__init__(*args)

    def __getattr__(self, fn, *args, **kwargs):
        lst = []
        if fn in dir(self[0]):
            for i in range(len(self)):
                ret = getattr(self[i], fn)(*args, **kwargs)
                print(f"Member {i} : executed: returned {ret}")
                lst.append(ret)
            return lambda *args, **kwargs : lst
        else:
            raise AttributeError(f"{fn} : does not exist for the first memeber. Note that heterogenous sets are not supported.")