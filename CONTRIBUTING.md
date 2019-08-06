## Implement
- [Implement](#implement)
  - [Coding Style](#coding-style)
  - [Writing a Test](#writing-a-test)

### Coding Style
This section will outline the coding rules for contributing to the Raiden Wizard repository. All code you write should strive to comply with these rules.

__Python__

All Python code follows the official Python style guide [PEP8](https://www.python.org/dev/peps/pep-0008/).
* __Formatting__

    For formatting we use the automatic formatter [Black](https://github.com/psf/black). The configurations for black are set in `pyproject.toml` and to format your code simply run:
    ```
    make black
    ```
    This will ensure that you comply with our formatting rules.

    We highly recommend you also use the other linting tools for automatically determining any style violations. All customizable options for pylint are set in `.pylint.rc`.

    Any pull request needs to pass:
    ```
    make lint
    ```
* __Line Length__

    We have a hard limit on a maximum line length of __99 characters__. `Flake8` will warn you if you exceed this limit.

    We also have a soft limit of __80 characters__ which is not enforced but just there to encourage shorter lines.

    Sometimes `Black` will reformat lines so they go above the hard limit of 99 characters. In such cases try to break up expressions, e.g.

    Bellow example will fail the `Flake8` test on `make lint`.
    ```python
    def testalongline(a):
        mysum = int(
            sum(
                content.value.amount
                for content in a.internal_field.fields_internal_long_named_dictionary_variables.values()
            )
        )
        return mysum
    ```
    Change it to:
    ```python
    def testalongline(a):
        mysum = sum(
            content.value.amount
            for content in a.internal_field.fields_internal_long_named_dictionary_variables.values()
        )
        mysum = int(mysum)
        return mysum
    ```
* __Shadowing Builtins__

    Pylint will warn you if you try to shadow built-in names. If you want to use a built-in name add a trailing underscore. The name `type` would for example become `type_`.

    Don't use leading underscores like `_type` since these are reserved for private attributes.
* __Docstrings__

    For docstrings we follow [PEP 0257](https://www.python.org/dev/peps/pep-0257/#multi-line-docstrings).

    A single line docstring should look like this:
    ```python
    def a(b: B, c: C) -> D:
        """Here be docs"""
        pass
    ```
    A multi-line docstring should look like this:
    ```python
    def a(b: B, c: C) -> D:
        """ Function Title

        body comes
        here
        """
        pass
    ```
    *Note that the multi-line docstring has a title and a body.*

* __Naming Convention__

    Use descriptive variable names and avoid short abbrevations.

    Good practice:
    ```python
    manager = Manager()
    balance_holder = AccountBalanceHolder()
    service = RaidenService()
    ```
    Bad practice:
    ```python
    mgr = Manager()
    a = AccountBalanceHolder()
    s = RaidenService()
    ```
    We have introduced some rules for keeping a consistent naming convention throughout the codebase and make it easy for any reader of the code to understand it.

    __Addresses__
    * Use `<name>_address_hex` for hex encoded addresses.
    * Use `<name>_address` for binary encoded addresses.

    __Lists of Objects__
    * Use `<name>s`. For a list `Channel` object instances it would be `channels`.
    * Use `list()` instead of `[]` to initialize an empty list.

        *This is only for style consistency and may change in the future because it might provide a tiny [change in performance](https://stackoverflow.com/questions/5790860/and-vs-list-and-dict-which-is-better).*
    
    __Mappings/Dicts__
    * Use `<name>_to_<name>` for simple one to one mappings, e.g. `tokenaddress_to_taskmanager`.
    * Use `<name>_to_<name>s` (an added `s`) if the mapped object is a list, e.g. `<tokenaddress_to_taskmanagers>`.
    * Use `dict()` instead of `{}` to initialize an empty dict.

        *This is only for style consistency and may change in the future because it might provide a tiny [change in performance](https://stackoverflow.com/questions/5790860/and-vs-list-and-dict-which-is-better).*

    __Class Attributes and Functions__
    * Class members should be private by default and start with a leading underscore `_`.
    * Anything that is part of the interface of the class should not have a leading underscore.
    * Other parts of the code should only use the class through the public interface.
    * Our tests should be testing the public interface of the class.
    
        A minimal example:
        ```python
        class Diary:
            def __init__(self, entries: List[str]) -> None:
                self._entries = entries

            def entry(index: int) -> str:
                return _entries[index]
        ```
        *Note the typing of `__init__(...) -> None:`*

    __NewTypes and Type Comparisons__
    * For often used types define new types using the `typing.NewType` function. New type names should be capitalized.
        ```python
        Address = NewType('Address', bytes)
        ```
        You need to define an associate alias which starts with `T_` in order to use these type definitions for type comparisons.
        ```python
        T_Address = bytes
        ```

    __typing.Optional Convention__
    * If the argument has a default value of `None` we follow the convention to omit the use of `typing.Optional[]`.

        Good Practice:
        ```python
        def foo(a: int = None) -> ReturnType:
        ```
        Bad Practice:
        ```python
        def foo(a: typing.Optional[int] = None)
        ```

    __Imports__

    Classes must be imported in the global namespace unless there are name collisions and module imports can be used.
    ```python
    import a
    from b import Normal


    class Conflict:
        pass


    def f() -> Tuple[a.Conflict, Normal]:
        return a.Conflict(), Normal()
    ```
### Writing a Test
You should always start by writing a __test__ or modifying __existing tests__ when developing a feature or working on a bug fix.
1. Write a test and see it fail.
2. Implement the feature/bug fix.
3. Confirm that all your new tests pass.

Your addition to the test suit should test your feature/bugfix at the innermost level possible. Avoid integration tests in favor of unit tests whenever possible.