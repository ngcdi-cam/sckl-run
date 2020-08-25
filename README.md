# sckl-run

## Building sckl-core

```
$ git clone https://github.com/ngcdi-cam/sckl-core -b dev --depth=1
$ cd sckl-core
$ sbt docker:publishLocal
$ cd ..
```

## Building restful-mininet and network awareness

```
$ git clone https://github.com/ngcdi-cam/restful-mininet-ryu --recursive --depth=1
$ cd restful-mininet-ryu/mininet
$ docker build -t mbyzhang/mininet .
$ cd ../ryu
$ docker build -t mbyzhang/awareness .
$ cd ../..
```

## Installing `run_containers.py`

```
$ git clone https://github.com/ngcdi-cam/run_containers --depth=1
$ cd run_containers
$ pip3 install --user -r requirements.txt
$ sudo install -m 755 run_containers.py /usr/local/bin
$ cd ..
```

## Running the experiment

```
$ git clone https://github.com/ngcdi-cam/sckl-run --recursive
$ cd sckl-run
$ pip3 install --user -r requirements.txt
$ python3 run_experiments.py
```