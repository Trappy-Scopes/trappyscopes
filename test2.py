def fn_(fn, *args, **kwargs):
    args_str = str(list(args)).strip('[').strip(']')
    optional_comma = ', '*(len(args)!=0 and len(kwargs) != 0)
    kwargs_str = ""
    for i, key in enumerate(kwargs):
        if isinstance(kwargs[key], str):
            obj = f"'{str(kwargs[key])}'"
        else:
            obj = str(kwargs[key])
        kwargs_str += (str(key) + "=" + obj)
        if i != len(kwargs)-1:
            kwargs_str += ", "
    
    return f"{fn}({args_str}{optional_comma}{kwargs_str})"

print(fn_("do", "1", 2, 3, kwg=123, sf="dsfs", sf2=12.23, sft=True, sfx=12))
print(fn_("do"))
