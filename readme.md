## Build

```bash
pyinstaller main.spec
```

Build target: `./dist/main/main.exe` : UI

`./dist/main/sender.exe` : Utill to emulate remote terminals sending images

### Usage

#### UI

Copy config files from `./dist/required` and  directory  `./models` (including the folder) to build directory ( `./dist/main`), then

```bash
./main.exe
```

#### Testing

Optionally, copy test images from `./dist/testfiles` to build directory (`./dist/main`)

- Send testfiles/testYL.png as ID: AAYL-999999-AAAAA

  ```bash
  ./sender.exe -i ./testfiles/testYL.png -n AAYL-999999-AAAAA
  ```
