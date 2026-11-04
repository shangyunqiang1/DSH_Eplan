# The EOX file — structure and safe editing

An `.eox` is EEC Pro's model exchange file: libraries plus projects, as exported by the Designer and loaded
by the Job Server (`model=` in a recipe). These notes come from editing EOX files programmatically.

## Layout

An EOX is a **zip** with one entry per library or project, each an XML "fibabean":

```
Engineering/data/__c__.eo          system libraries (Engineering, ECAD, Plc, JobServer, Office, …)
ECAD/data/__c__.eo
<YourLibrary>/data/__c__.eo         your library: classes, typicals, macros, actions, parameter pools
<Project>/data/__c__.eo             the project (e.g. NewProject): instances, configured values
mind8_modelvariables/data/__c__.eo  model variables (ecad_*_parameter_name, …)
mind8_authorization/data/__c__.eo   roles
mind8_ProjectForParentLessEOs/…Root.eo
```

```xml
<fibabean checksum="1580501553" isa="com.mind8.mechatronic.skill.eos.Library">
   <skill n="…" v="…"/>            <!-- versions of the EEC skills that wrote it -->
   <ck v="8206580768555228610"/>   <!-- object id -->
   <c n="topLevelLibraryClass"> <eo isa="…TopLevelLibraryClass"> <a n="name" v="Office"/> … </eo> </c>
   <c n="imports">
      <eo isa="com.mind8.mechatronic.skill.eos.ImportQualifier">
         <ck v="…"/> <a n="reexport" v="true"/>
         <r n="importedLibraryReference"> <ck v="Engineering"/> </r>
      </eo>
   </c>
</fibabean>
```

- **`<eo>`** is an object, **`<a n= v=>`** an attribute, **`<c n=>`** a containment, and **`<r n=>`** a
  reference.
- **References are by qualified name** (`<ck v="Library.Package.Class"/>`), so moving objects between
  libraries means rewriting those names.
- **Every `<eo>` has a `<ck v="…"/>` id.** Ids must be unique within a file and across the files of the
  model.
- **The `checksum` attribute must be recomputed** after any edit, or EEC rejects or ignores the entry. Keep a
  rechecksum tool in the pipeline and run it after every patch step.

## Libraries import libraries

- **Imports are declared per library** with `ImportQualifier` → `importedLibraryReference`. A project
  imports its libraries the same way.
- **The root entry is empty, so there is no central registry.** A library is "in the model" when its zip
  entry exists and something imports it.
- **A shared library can be added to many models:**
  1. write `<Lib>/data/__c__.eo`, importing `Engineering`, holding a `ResourcePackageClass` with your
     classes;
  2. add an `ImportQualifier` for it to the project;
  3. recompute the checksums.

  Job Server workers load it and run its actions (verified). Generate it with **deterministic ids**, for
  example a hash of the object path. The file is then byte-identical in every model, and updating all
  models means replacing one zip entry each.
- **This is the clean way to share logic** (actions, helpers) across many machine models: one source and one
  regenerated entry, instead of patching every model.

## Editing safely

- **Never hand-edit inside the Designer and by script at the same time.** Pick one source of truth for each
  part of the model.
- **Write to a new file.** Open the output zip in exclusive-create mode so a typo never overwrites a
  deployed model.
- **Byte-level replacement inside zip entries** is fine for mechanical changes (for example, renaming a
  resource folder that appears in thousands of macro paths). Count the replacements, and also count any
  remaining occurrences in other spellings (`/`, `\\`).
- **Python `zipfile`:** read each entry exactly once and keep the bytes. A second `read()` of the same entry
  in one archive can raise `BadZipFile: Overlapped entries` on EEC-written zips.
- **After every patch, run an integrity check:**
  - duplicate `ck` within and across entries;
  - library references (`<r><ck v="Lib.Path"/></r>`) that do not resolve to an object with that path.

  One unresolved `origin` id in the project is normal.

## Resource paths and versions

- **Build machine models with resource paths that are complete from the global resource root**, for
  example `FAMILY\MACHINE\v12\ECAD\Macros\…`. The Job Server worker resolves against the global root, so
  the Designer and the worker then see the same files and nothing has to be copied into a shared `ECAD`
  folder.
- **Name version folders after the version the input data carries.** For example, the field the
  configuration JSON already sends per entity. A dispatcher can then route by that value and reject inputs
  whose version is not deployed, instead of silently generating with the wrong model.
