# Trappy Scopes Control Layer

A quick how-to-trap guide.


## 0. Login
+ `User.login("CC")` : log user in.
+ `User.logout` : log user out.


## 1. Create an `Experiment` 
+ `exp = Experiment(new_exp_name)` : create a new experimet.
+ `exp = findexp()` : would open a prompt where you can search the experiment by name.
+ `exp.close()`  : to close the experiment.
+ `exp.sync_dir()` : to synchronise the experiment directory on the file server.
+ `ScripEngine.now(globals(), "scripts/folder/scriptname.py")` : to run the script now.
+ `exp.params/exp.attribs` : is a dictionary of all the control parameters.
+ `Experiment.current` holds the current experiment object.


## 2. Use the Scope
+ `scope` is `ScopeAssembly.current`
+ `scope.draw_tree()` : to inspect the scope.
+ `scope.lit.setVs(2,0,0)` : to set lights.
+ `scope.cam.read("img", "test.png")` : record a picture.

## 3. Understand
+ Use `help(object/fn)` or better `explorefn()` to find out what it does.
+ Use `codeviewer()` to directly inspect code in the terminal in a safe fashion.