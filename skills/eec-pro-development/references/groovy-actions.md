# Groovy actions, generation sequence and the P8 post-generation script

Custom recipe actions are `ActionClass` objects in a library, with a static `run` method whose code is
Groovy (`language="java"` in the EOX). The scripting references are `refscripting` and `eecscripting`.
These are field notes on what works inside EEC's scripting runtime.

## Shape of an action in the EOX

```xml
<eo isa="com.mind8.mechatronic.skill.eos.ActionClass">
   <ck v="…"/> <a n="isAbstract" v="false"/> <a n="name" v="CloseBatchAction"/>
   <c n="methods">
      <eo isa="com.mind8.mechatronic.skill.eos.TypeMethod">
         <ck v="…"/> <a n="code" v="…escaped Groovy…"/>
         <a n="isStatic" v="true"/> <a n="language" v="java"/> <a n="name" v="run"/>
         <c n="arguments">
            <eo isa="com.mind8.mechatronic.skill.eos.Argument"> <ck v="…"/> <a n="name" v="fileName"/>
               <r n="typeReference"> <ck v="Engineering.String"/> </r> </eo>
         </c>
      </eo>
   </c>
   <r n="superTypeReference"> <ck v="Engineering.Action"/> </r>
</eo>
```

- **Recipe call:** `<action name="Lib.Package.CloseBatchAction" arguments="=List{trigger.fileName}"/>`.
  Arguments bind by position to the declared arguments, typed as `Engineering.String`, `Engineering.Map`, …
- **Sequence actions** (`SequenceSelectionActionClass`, `language="sequence"`) only chain commands with
  `MethodCaller`. Read them to learn the exact command order the vendor uses.

## Groovy runtime pitfalls (ScriptingMetaClass)

- **No closures** (`{ x -> … }`, `each`, `collect`). Use plain `for` loops.
- **No `getClass().getName()`.** Use `instanceof` checks.
- **A line that starts with `+` is a new statement.** Keep the `+` at the end of the previous line when
  concatenating across lines:
  ```groovy
  String s = "a" +
      "b";        // right
  String t = "a"
      + "b";      // WRONG: t == "a"
  ```
- **Numbers from `groovy.json.JsonSlurper`** come back as `BigDecimal`/`BigInteger`. Convert them to
  `Integer`/`Long`/`Double` before handing a map to EEC commands, or you get `DataTypeNoLiteralException`.
- **Logging:** a `SpaceLogger` goes to the worker log. For messages visible in the Job Server log tree, use
  `UserMessageCollector.addWarning(PROJECT, self, null, category, text)`, wrapped in try/catch.
- **Calling commands from Groovy:**
  ```groovy
  ((CommandClass) TypeClass.findType(self.getUnitOfWork(), "Engineering.SendMailCommand"))
      .perform("execute", from, to, cc, bcc, subject, htmlBody, "", "");
  ((CommandClass) TypeClass.findType(self.getUnitOfWork(), "JobServer.SetProgressMessageCommand"))
      .perform("execute", text);
  ```
- **Objects and parameters:**
  ```groovy
  Object o = AbsoluteNameUtil.getObjectByAbsolutePath("Project.Mechatronic.Typical.Part", self.getUnitOfWork());
  o.getParameter("SomeParam").setPrettyValue("=Map{Pair{'Key','value'}}");   // formula text
  self.getUnitOfWork().saveChanges();
  ```
- **Check generated code locally before deploying.** Compile it with the Groovy jars that ship with EEC
  (`…\configuration\org.eclipse.osgi\…\.cp\lib\groovy-*.jar`) up to semantic analysis. Only "unable to
  resolve class" for EEC-internal classes is expected. Simulate concurrency-sensitive logic against a local
  folder with stub objects.

## Feeding a JSON input file into the model

- **`Engineering.SetParameterValueFromJsonCommand`** with an already-parsed `Map` works.
- **The `…FromJsonFileCommand` variant can report "successful" and write nothing** if it targets a
  parameter you do not have. Verify, and when in doubt read the file in Groovy and call the map variant.
- **To see what the model actually received**, add an export temporarily after generation:
  `Engineering.ExportEOXCommand` with `=List{trigger.additionalResultsDir + 'eox\\Model.eox', List{'Project'}}`.
  Then inspect the configured value in the exported EOX.

## The ECAD generation sequence

A vendor-style "generate the P8 project" sequence is:

```
Engineering.StartFormulaCacheCommand
ECAD.GenerateEcadStructureCommand(MechatronicRoot)
Engineering.StopFormulaCacheCommand
Engineering.StartFormulaCacheCommand
ECAD.GenerateEcadProjectCommand(Root)        // overloads: Engineering.Root | ECAD.WiringDiagram | Engineering.List
Engineering.StopFormulaCacheCommand
```

- **Call it as one sequence action.** Splitting it into separate recipe actions runs without errors but
  generates an **empty** project: the project step does not see the structure the previous action built.
- **`GenerateEcadProjectCommand` needs an `Engineering.Root`.** Pass the mechatronic root
  (`absRef('Project.Mechatronic')`). `absRef('Project')` is a `ProjectRootPackage` and fails with "Method
  'execute' with parameters '(ProjectRootPackage)' not found".
- **`GenerateEcadStructure` regenerates the ECAD copy of the wiring diagram** (`Project.ECAD.Project`) from
  its origin, the mechatronic wiring diagram. Values set on the copy before generation are lost: set them on
  the mechatronic object.

## P8 post-generation script and `ScriptArguments`

- **Model variables** name the wiring-diagram parameters EEC uses:
  - `ecad_p8_script_parameter_name` (usually `Script`): path of a C# script that P8 runs after generation;
  - `ecad_p8_script_parameter_argument_name` (usually `ScriptArguments`): a `Map`.
- **EEC passes each map entry by name** to a `string`/`int` parameter of the script's `[Start]` method:
  ```csharp
  [Start] public void Export(string ProjectName, string Destination) { … }
  ```
  `ProjectName` is the generated `.elk` path.
- **Set the map per job** from a Groovy action that runs before generation. Use `setPrettyValue` on the
  **mechatronic** wiring diagram, then `saveChanges`. This is how a job tells its script where to publish
  results (a share path built from the trigger file name), since the project itself only reaches the share
  after the job ends.
- **Inside the script:**
  - export what other jobs need, for example `PageMacro.Create` of all pages into an `.emp`;
  - copy it to the target as `.tmp` and then `File.Move`, so readers never see a partial file;
  - write a small JSON report (pages, bytes, timings).

  EPLAN does not surface script exceptions well, so always leave a result or error file.
- **Scripts that EEC runs inside EPLAN 2025 compile as C# 5.** Resolve API types by reflection if the script
  must run in several EPLAN versions. Check compilation locally with `LangVersion 5` against stubs.

## Configuration outside the model

- **Keep environment values out of the compiled Groovy:** root folders, queue tables, mail sender, template
  paths. Put them in one JSON file on the share that actions read at run time (`JsonSlurper`), with the
  compiled values as fallback when the file is missing or broken.
- **Then only the config file's own path is compiled in.** Routing a new machine or version becomes a
  config edit instead of a model rebuild and redeploy.
