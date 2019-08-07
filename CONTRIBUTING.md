# Raiden Wizard Development Guide
Welcome! These are the guidelines for anyone interested in contributing to the Raiden Wizard codebase.

## Creating an Issue
[For Feature Requests](#for-feature-requests)
[For Bugs](#for-bugs)

### For Feature Requests
If you want to request a feature for the Raiden Wizard you can do so by opening an issue that contains:
* A description of the feature you would like to see implemented.
* A explanation of why you believe the feature would make a good addition to the Raiden Wizard.

### For Bugs
If you experience a problem while using the Raiden Wizard you can address the problem by opening an issue that contains:
* A short description of the problem.
* A detailed description of your system.
* A description of what exact unexpected thing that occurred.
* What you were expecting to happen instead.

## Implementation
  - [Coding Style](#coding-style)
  - [Writing a Test](#writing-a-test)
  - [Documentation](#documentation)
  - [Committing Rules](#committing-rules)
  - [Opening a Pull Request](#opening-a-pull-request)
  - [Integrating Pull Requests](#integrating-pull-requests)

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
When developing a feature or working on a bug fix you should always start by writing a __test__ or modifying __existing tests__.
1. Write a test and see it fail.
2. Implement the feature/bug fix.
3. Confirm that all your new tests pass.

Your addition to the test suit should test your feature/bug fix at the innermost level possible. Avoid integration tests in favor of unit tests whenever possible.
### Documentation
Code should be documented.
### Committing Rules
You can read this [guide](https://chris.beams.io/posts/git-commit/) which has really good advice but some rules you should always follow are:
* Commit titles should not exceed __50 characters__.
* Leave a blank line after the title (this is optional if there is no description)
* Leave a description of the commit (this is optional if the commit is really small)

Why are these rules important?

All tools that show you information about git repos treat the first 80 characters as a title. Even GitHub itself does so and the git history will look nice and neat if these simple rules are followed.
### Opening a Pull Request
If you would like to contribute to the actual codebase you can open a pull request against the repository.

All pull requests should be:
* Self-contained.
* As short as possible, addressing a single issue or even a part of an issue.


    *Consider breaking long pull requests into smaller ones.*

To get your pull request merged into the main repository it needs to:
* Have one approved review from one of the core developers.
* All Continuous Integration tests needs to pass and the CI build should be green.

You also need to sign the Raiden project CLA (Contributor License Agreement), our CLA bot will help you with that after you created your pull request. If you or your employer do not hold the whole copyright of the authorship submitted we can not accept your contribution.

__For Frequent Contributors with Write Access__

We have a set of labels to put on pull requests for signaling to colleagues what the current state of the pull request is.

These are:
* [Dev: Please Review](https://github.com/raiden-network/raiden/labels/dev%3A%20Please%20Review)

    Pull requests that are ready for a reviewer to have a look at.

* [Dev: Work in Progress](https://github.com/raiden-network/raiden/labels/dev%3A%20Work%20In%20Progress)

    Pull requests that are either not ready for review or are getting review suggestions applied by the author.

__Pull Request Reviews__

It is the authors responsibility to ask for at least one person to review their pull request. This person should know the area of the code being changed. If the chosen reviewer does not feel fully confident in doing the review they can ask someone else to take an additional look at the code.

All developers in the team should perform pull request reviews. Make it a habit to check [this](https://github.com/raiden-network/raiden/pulls?q=is%3Apr+is%3Aopen+label%3A%22dev%3A+Please+Review%22) link often to help colleagues who have pull requests pending for review.

We have tools that are automatically run by the CI and which check the quality of the code (flake8, mypy, pylint). Fixes related to linting are therefore not part of pull request reviews.

Reviewers are encouraged not to be nitpicky about the suggested changes they are asking the author for. If something is indeed nitpicky the reviewer is encouraged to state it beforehand so that the author can choose whether to implement the nitpicks or ignore them.

Good practice:
> nitpick: I don't really think XYZ makes sense here. If possible it would be nice to have it changed to KLM.

Authors should strive to make pull request reviews easier.
* Make the pull requests as small as possible.
* Even if some code is touched it doesn't mean it needs to be refactored, e.g. don't mix style/typing change with a big pull request.

Whenever a reviewer starts to review a pull request he or she should write a comment in the pull request stating they are doing so, e.g. "Reviewing this now". This is for keeping track of who is reviewing a pull request and when a review is going on.

When performing a pull request review of non trivial pull requests it is recommended to clone the branch locally, explore the changes with your editor, run tests and experiment with the changes to get a better understanding of the code changes and good constructive feedback can be given to the author.
### Integrating Pull Requests
There are two options for integrating a successful pull request into the codebase.
* __Create a Merge Commit__

* __Rebase and Merge__

"Create a Merge Commit" is the GitHub default option which unfortunately is __not__ our preferred option since we can not be sure that the result of the merge will have all test passing. This is because there may be other patches merged since the pull request opened.

There are many pull requests which we definitely know won't have any conflicts and for which enforcing rebase would make no sense therefore we provide the option to use both at our own discretion.

The general guidelines are:
* Use __Rebase and Merge__ if patches have been merged to master since the pull request was opened on top of which our pull request may have different behaviour.
* Use __Create a Merge Commit__ if patches have been merged to master since the pull request was opened which are related to documentation, infrastructure or completely unrelated parts of the code.