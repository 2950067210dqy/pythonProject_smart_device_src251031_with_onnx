## Build

```bash
pyinstaller main.spec
```

Build target: `./dist/main/main.exe` : UI

`./dist/main/sender.exe` : Utill to emulate remote terminals sending images

### Move to Build Directory
```bash
cd ./dist/main/
```
### Usage

#### UI

Copy config files from `./dist/required/*.ini` and  directory  `./models` (including the folder)  and  directory `./dist/testfiles/TESTIMAGES` (including the folder)  to build directory ( `./dist/main`), then

```bash
./main.exe
```

#### Testing

Optionally, copy test images from `./dist/testfiles` to build directory (`./dist/main`)

- Send testfiles/testYL.png as ID: AAYL-999999-AAAAA

  ```bash
  ./sender.exe -i ./testfiles/testYL.png -n AAYL-999999-AAAAA
  ```

- Or Send random Images from directory `./dist/testfiles/TESTIMAGES`    **(Main USING)**

  ```bash
  ./sender.exe
  ```
