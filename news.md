 - update install requires - don't think whitequark is still pushing to pypi

 - follow pep setup.py suggestions allowing for easy testing and 
sane imports
   - remove relative imports
   - ```python3 setup.py test``` now works
 - replace dependency of internal nmigen FHDLTestCase using ```nmigen.test.utils``` (which whitequark has already deprecated) - formal tests still passing
 - remove unused signals from L1Cache - formal tests still passing
 - add README link to Minerva "hello world"
 - add "hello world" as test case