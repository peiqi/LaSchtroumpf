package main

import (
	. "fmt"
)

type Node struct {
	data int
	next *Node
}

func Create() *Node {
	// create a list of 5 nodes
	var Head *Node = new(Node)
	//memset(Node, 0, sizeof(*Node));
	tmp := Head
	for i := 0; i < 5; i++ {
		q := new(Node)
		tmp.next = q
		q.data = i
		q.next = nil
		tmp = q

		//fmt.Println(tmp.data)
	}
	return Head.next
}

func Reverse(head *Node) *Node {

	current := head.next
	tmp := current.next
	if current != nil {
		current.next = head
		head = current
		head.next = nil
	}
	for tmp != nil {
		current = tmp
		tmp = tmp.next
		current.next = head
		head = current
	}
	return head
}

func main() {
	head := Create()
	Head := Reverse(head)
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
