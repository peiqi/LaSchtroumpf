package main

import (
	. "fmt"
	 "os"
	 "strconv"
)

type Node struct {
	data int
	next *Node
}

func Create(N int) *Node {
	// create a list of 5 nodes
	var Head *Node = new(Node)
	//memset(Node, 0, sizeof(*Node));
	tmp := Head
	for i := 0; i < N; i++ {
		q := new(Node)
		tmp.next = q
		q.data = i
		q.next = nil
		tmp = q

		//fmt.Println(tmp.data)
	}
	return Head.next
}

func (head *Node) Reverse() *Node {

	current := head.next
	tmp := current.next
	if current != nil {
		current.next = head
		head.next = nil
		head = current
	}
	for tmp != nil {
		current = tmp
		tmp = tmp.next
		current.next = head
		head = current
	}
	return head
}

func show(Head *Node){
	for {
		if Head.next != nil {
			toprint := Head.data
			Println(toprint)
			Head = Head.next
		} else {
			toprint := Head.data
			Println(toprint)
			break
		}
	}
}
func main() {
        number, _:= strconv.Atoi(os.Args[1])
	head := Create(number)
        Printf("the orignal list \n")
        show(head)
	Head := head.Reverse()
        Printf("after changed list \n")
        show(Head)
}
