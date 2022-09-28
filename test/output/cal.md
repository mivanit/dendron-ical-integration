# Events
## todo
 - [ ] [[#todo._log]] **test title**  
    a description  
    *origin:* [[test/source/test.md]] (line 1)  
    *time:* 2022-09-26 14:08 to 14:37 (duration: 0:30)  
  
    ```py
    {'_tag': '#todo', '_desc': 'test title | a description', '_done': False, 'due': '2022-09-26 14:08', '_raw': '- #todo {due="2022-09-26 14:08"} test title | a description\n', '_file': 'test/source/test.md', '_line': 1}
    ```

 - [ ] [[#todo._log]] **do this today!**  
    no, seriously, do it today  
    *origin:* [[test/source/test.md]] (line 3)  
    *time:* 2022-09-28 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'do this today! | no, seriously, do it today', '_done': False, 'due': 'today', '_raw': '- #todo {due="today"} do this today! | no, seriously, do it today\n', '_file': 'test/source/test.md', '_line': 3}
    ```

 - [ ] [[#todo._log]] **do tmro**  
    this can wait  
    *origin:* [[test/source/test.md]] (line 5)  
    *time:* 2022-09-29 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'do tmro | this can wait', '_done': False, 'due': 'tmro', '_raw': '- #todo {due="tmro"} do tmro | this can wait\n', '_file': 'test/source/test.md', '_line': 5}
    ```

 - [ ] [[#todo._log]] **all day today**  
    a description  
    *origin:* [[test/source/test.md]] (line 7)  
    *time:* 2022-09-28 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'all day today | a description', '_done': False, 'due': '2022-09-28 14:08', 'allday': True, '_raw': '- #todo {due="2022-09-28 14:08" .allday} all day today | a description\n', '_file': 'test/source/test.md', '_line': 7}
    ```

 - [ ] [[#todo._log]] **another thing all day today**  
    a description  
    *origin:* [[test/source/test.md]] (line 9)  
    *time:* 2022-09-29 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'another thing all day today | a description', '_done': False, 'due': '2022-09-29', '_raw': '- #todo {due="2022-09-29" } another thing all day today | a description\n', '_file': 'test/source/test.md', '_line': 9}
    ```

 - [x] [[#todo._log]] **this thing is done!**  
    (no description)  
    *origin:* [[test/source/test.md]] (line 11)  
    *time:* 2022-09-30 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'this thing is done!', '_done': True, 'due': '2022-09-30', 'done': True, '_raw': '- #todo {due="2022-09-30" .done} this thing is done!\n', '_file': 'test/source/test.md', '_line': 11}
    ```

 - [ ] [[#todo._log]] **still have to do this**  
    a description  
    *origin:* [[test/source/test.md]] (line 13)  
    *time:* 2022-09-26 14:08 to 14:37 (duration: 0:30)  
  
    ```py
    {'_tag': '#todo', '_desc': 'still have to do this | a description', '_done': False, 'due': '2022-09-26 14:08', '_raw': '- [ ] #todo {due="2022-09-26 14:08"} still have to do this | a description\n', '_file': 'test/source/test.md', '_line': 13}
    ```

 - [x] [[#todo._log]] **done, but with checkmark**  
    a description  
    *origin:* [[test/source/test.md]] (line 15)  
    *time:* 2022-09-26 14:08 to 14:37 (duration: 0:30)  
  
    ```py
    {'_tag': '#todo', '_desc': 'done, but with checkmark | a description', '_done': True, 'due': '2022-09-26 14:08', '_raw': '- [x] #todo {due="2022-09-26 14:08"} done, but with checkmark | a description\n', '_file': 'test/source/test.md', '_line': 15}
    ```

 - [x] [[#todo._log]] **this, thing; has weird characters**  
    more weird chars: ! @ # $ % ^ & * ( ) _ + - = [ ] : ; " ' < > , . ? / \ | ` ~  
    *origin:* [[test/source/test.md]] (line 17)  
    *time:* 2022-09-30 (all day)  
  
    ```py
    {'_tag': '#todo', '_desc': 'this, thing; has weird characters | more weird chars: ! @ # $ % ^ & * ( ) _ + - = [ ] : ; " \' < > , . ? / \\ | ` ~', '_done': True, 'due': '2022-09-30', '_raw': '- [x] #todo {due="2022-09-30"} this, thing; has weird characters | more weird chars: ! @ # $ % ^ & * ( ) _ + - = [ ] : ; " \' < > , . ? / \\ | ` ~\n', '_file': 'test/source/test.md', '_line': 17}
    ```

