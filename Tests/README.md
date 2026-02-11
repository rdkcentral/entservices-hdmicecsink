As part of rdkservices open source activity and logical grouping of services into various entservices-* repos, the below listed change to L1 and L2 Test are effective hence forth.

# Changes Done:
Since the mock part is common across various plugins/repos and common for L1, L2 & etc, the gtest and gmock related stubs (including platform interface mocks) are moved to a new repo called "entservices-testframework" and L1 & L2 test files of each plugin moved to corresponding repos, you can find them inside Tests directory of each entservices-*.
Hence, any modifications/additions related to mocks should be commited to entservices-testframework repo @ rdkcentral and any modifications/additions related to test case should be commited to Test directory of corresponding entservices repo.

# Individual Repo Handling
Each individual entservices-* repo was added with a .yml file to trigger L1, L2, L2-OOP test job in github workflow. This yml file triggers below mentioned build jobs in addition to regular build jobs (thunder, thunder tools & etc,).
```
a/ Build mocks => To create TestMock Lib from all required mock relates stubs and copy to install/usr/lib path.
b/ Build entservices-<repo-name> => To create Test Lib of .so type from all applicable test files which are enabled for plugin test.
c/ Build entservices-testframework => To create L1/L2  executable by linking the plugins/test .so files.
```
This ensures everything in-tact in repo level across multiple related plugins when there is a new change comes in.

##### Steps to run L1, L2, L2-OOP test locally #####
```
1. checkout the entservices-<repo-name> to your working directory in your build machine.
example: git clone https://github.com/rdkcentral/entservices-deviceanddisplay.git

2. switch to entservices-<repo-name> directory
example: cd entservices-deviceanddisplay

3. check and ensure current working branch points to develop
example: git branch

4. Run below curl command to download act executable to your repo.
example: curl -SL https://raw.githubusercontent.com/nektos/act/master/install.sh | bash

5. Run L1, L2, L2-oop test
example: ./bin/act -W .github/workflows/tests-trigger.yml -s GITHUB_TOKEN=<your access token>

NOTE: By default test-trigger.yml will trigger all tests(L1, L2 and etc) parallely, if you want any one test alone to be triggered/verified then remove the other trigger rules from the tests-trigger.yml
```
# testframework Repo Handling
tf-trigger.yml file of testframework repo will get loaded into github action whenever there is a pull or push happens. This file in-turn triggers all individual repos L1, L2, L2-oop tests. testframework repo test can run only in github workflow.

NOTE:
If you face any secret token related error while run your yml, pls comment the below mentioned line
#token: ${{ secrets.RDKE_GITHUB_TOKEN }}

# Execution usecases where manual change required before triggering the test:
```
a/ changes in testframework repo only:
Need to change ref pointer of "Checkout entservices-testframework" job in individual repo yml file, to point your current working branch of testframework and in tftrigger.yml of testframework repo need to change trigger branch name to your individual repo branch name instead of develop which is default.
example:
ref: topic/method_1  /* Checkout entservices-testframework job */
uses: rdkcentral/entservices-deviceanddisplay/.github/workflows/L1-tests.yml@topic/method_1 /* tf-trigger.yml */

b/ changes in both testframework repo and invidual repo:
Changes mentioned in step (a) above + "Checkout entservices-deviceanddisplay-testframework" job in individual repo yml file, ref field to point your deviceanddisplay current working branch.
example:
ref: topic/method_1 /* Checkout entservices-testframework job */
ref: topic/method_1 /* Checkout entservices-deviceanddisplay-testframework job */
uses: rdkcentral/entservices-deviceanddisplay/.github/workflows/L1-tests.yml@topic/method_1 /* tf-trigger.yml */

c/ changes in individual entservices-* repo only
no changes required
```
