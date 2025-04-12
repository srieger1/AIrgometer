#!/usr/bin/env bash
 curl -X POST -H "Content-Type: application/json" -d '{ "watt_seconds": 10}' http://localhost:5000/submit_watt_seconds