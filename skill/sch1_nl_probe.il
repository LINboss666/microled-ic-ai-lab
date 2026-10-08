printf("NP-BEGIN\n")
foreach(f list('nlNetlist 'nlCreateDesign 'nlCreateFormatter 'hnlNetlist 'dbNetlist 'apskNetlist
               'apskCreateSession 'apskFindSession 'adeGetVal 'adeSetVal 'oasRefresh 'netlist 'nlNetlister
               'nlSetOption 'nlGetOption 'nlAddExtraParameters 'asiCreateSession 'asiOpen 'sessionOpen)
  printf("NP %L => %L\n" f getd(f))
)
printf("NP_DONE\n")
exit()
