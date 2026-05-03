# TEST POLICY

- DO NOT run all tests at once. The test suite is 700+ tests and this computer is old. It will time out and you will whine and give up on testing. This is unacceptable and *stupid.* DO NOT DO THIS. 

- Run groups of tests IN PARALLEL as parallel bash commands. If for whatever reason you cannot do this, run them one by one.

- Either way, DO NOT RUN PYTEST ON THE ENTIRE TESTS/ DIRECTORY WITH ONE COMMAND. **DO NOT.**